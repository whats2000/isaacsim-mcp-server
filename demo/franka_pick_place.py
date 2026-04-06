"""Franka FR3 Pick-and-Place — ScriptNode action script.

RMPflow-based controller. setup() runs once, compute() every frame.
On timeline STOP the state resets so next Play reruns the sequence.
"""

import carb
import numpy as np
import omni.physx
import omni.timeline
import omni.usd

# ── Config ──────────────────────────────────────────────────
ROBOT_PATH = "/World/Franka"
CUBE_PATH = "/World/TargetCube"
APPROACH_HEIGHT = 0.15
# fr3_hand_tcp is the lowest point when gripper faces down.
# Fingers are ~4.5cm above TCP. For the fingers to straddle the
# cube center, TCP must go to cube_center_z or slightly below.
GRASP_Z_OFFSET = -0.005  # TCP goes 5mm below cube center
# Table2 center Y (0.35) minus Table1 center Y (-0.15) = 0.5
PLACE_OFFSET_Y = 0.5
CONVERGE_THRESH = 0.035
CONVERGE_FRAMES = 10
GRIPPER_OPEN = 0.04
GRIPPER_CLOSE = 0.0
GRIPPER_WAIT = 40
GRASP_ROT = np.array([0.0, 1.0, 0.0, 0.0])
WARMUP_FRAMES = 30  # frames to wait for physics to settle

# ── States ──────────────────────────────────────────────────
WARMUP = 0
INIT = 1
OPEN_GRIPPER = 2
APPROACH_PICK = 3
DESCEND_PICK = 4
CLOSE_GRIPPER = 5
LIFT = 6
APPROACH_PLACE = 7
DESCEND_PLACE = 8
RELEASE = 9
RETREAT = 10
DONE = 11
_SNAME = [
    "WARMUP",
    "INIT",
    "OPEN_GRIPPER",
    "APPROACH_PICK",
    "DESCEND_PICK",
    "CLOSE_GRIPPER",
    "LIFT",
    "APPROACH_PLACE",
    "DESCEND_PLACE",
    "RELEASE",
    "RETREAT",
    "DONE",
]

# ── Persistent state ────────────────────────────────────────
_state = WARMUP
_frame = 0
_converge_count = 0
_robot = None
_rmpflow = None
_art_policy = None
_art_ik = None
_cube_pos = None
_place_pos = None
_target = None
_tl_sub = None
_world = None


def _log(msg):
    carb.log_warn(f"[PickPlace] {msg}")


def _get_cube():
    try:
        physx = omni.physx.get_physx_interface()
        rb = physx.get_rigidbody_transformation(CUBE_PATH)
        if rb and rb.get("ret_val", False):
            p = rb["position"]
            return np.array([float(p[0]), float(p[1]), float(p[2])])
    except Exception:
        pass
    return None


def _ee():
    if _art_ik is None:
        return np.zeros(3)
    p, _ = _art_ik.compute_end_effector_pose()
    return p


def _grip(val):
    from isaacsim.core.utils.types import ArticulationAction

    c = _robot.get_joint_positions().copy()
    c[-2] = val
    c[-1] = val
    _robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=c))


def _rmp_step():
    if _art_policy is None:
        return
    action = _art_policy.get_next_articulation_action()
    _robot.get_articulation_controller().apply_action(action)


def _aim(pos, rot=None):
    if _rmpflow is not None:
        _rmpflow.set_end_effector_target(target_position=pos, target_orientation=rot)


def _converged(tgt):
    global _converge_count
    dist = np.linalg.norm(_ee() - tgt)
    if dist < CONVERGE_THRESH:
        _converge_count += 1
    else:
        _converge_count = 0
    return _converge_count >= CONVERGE_FRAMES


def _go(new_state):
    global _state, _frame, _converge_count
    _log(f"{_SNAME[_state]} -> {_SNAME[new_state]}")
    _state = new_state
    _frame = 0
    _converge_count = 0


def _on_tl(event):
    global _state, _frame, _robot, _rmpflow, _art_policy, _art_ik, _world
    if event.type == int(omni.timeline.TimelineEventType.STOP):
        _state = WARMUP
        _frame = 0
        _robot = None
        _rmpflow = None
        _art_policy = None
        _art_ik = None
        if _world is not None:
            _world.clear_instance()
            _world = None
        _log("Reset")


def setup(db=None):
    global _tl_sub
    if _tl_sub is None:
        tl = omni.timeline.get_timeline_interface()
        _tl_sub = tl.get_timeline_event_stream().create_subscription_to_pop(_on_tl)
        _log("setup()")


def compute(db=None):
    global _state, _frame, _world
    global _robot, _rmpflow, _art_policy, _art_ik
    global _cube_pos, _place_pos, _target

    # ── WARMUP: let physics settle, then create World ────────
    if _state == WARMUP:
        _frame += 1
        if _frame >= WARMUP_FRAMES:
            try:
                from isaacsim.core.api import World

                _world = World.instance()
                if _world is None:
                    _world = World(physics_dt=1.0 / 60.0, stage_units_in_meters=1.0)
                _world.initialize_physics()
                _log("World + physics initialized")
                _go(INIT)
            except Exception as e:
                _log(f"Warmup error: {e}")
        return True

    # ── INIT: create motion planning objects ─────────────────
    if _state == INIT:
        try:
            from isaacsim.core.prims import SingleArticulation
            from isaacsim.robot_motion.motion_generation import (
                ArticulationKinematicsSolver,
                ArticulationMotionPolicy,
                LulaKinematicsSolver,
                RmpFlow,
                interface_config_loader,
            )

            _robot = SingleArticulation(prim_path=ROBOT_PATH, name="franka_pp_sn")
            _robot.initialize()

            cfg = interface_config_loader.load_supported_motion_policy_config("FR3", "RMPflow")
            _rmpflow = RmpFlow(**cfg)
            _art_policy = ArticulationMotionPolicy(
                robot_articulation=_robot, motion_policy=_rmpflow, default_physics_dt=1 / 60.0
            )

            ik_cfg = interface_config_loader.load_supported_lula_kinematics_solver_config("FR3")
            _art_ik = ArticulationKinematicsSolver(
                robot_articulation=_robot,
                kinematics_solver=LulaKinematicsSolver(**ik_cfg),
                end_effector_frame_name="fr3_hand_tcp",
            )

            _cube_pos = _get_cube()
            if _cube_pos is None:
                _log("Cube not found")
                return True

            _place_pos = _cube_pos.copy()
            _place_pos[1] += PLACE_OFFSET_Y

            ee = _ee()
            _log(
                f"EE=[{ee[0]:.3f},{ee[1]:.3f},{ee[2]:.3f}] Cube=[{_cube_pos[0]:.3f},{_cube_pos[1]:.3f},{_cube_pos[2]:.3f}]"
            )
            _go(OPEN_GRIPPER)
        except Exception as e:
            _log(f"Init error: {e}")
            import traceback

            traceback.print_exc()
        return True

    # ── OPEN_GRIPPER ─────────────────────────────────────────
    if _state == OPEN_GRIPPER:
        _grip(GRIPPER_OPEN)
        _frame += 1
        if _frame >= GRIPPER_WAIT:
            _target = _cube_pos.copy()
            _target[2] += APPROACH_HEIGHT
            _aim(_target, GRASP_ROT)
            _go(APPROACH_PICK)
        return True

    # ── APPROACH_PICK ────────────────────────────────────────
    if _state == APPROACH_PICK:
        _rmp_step()
        _frame += 1
        if _converged(_target):
            _target = _cube_pos.copy()
            _target[2] += GRASP_Z_OFFSET
            _aim(_target, GRASP_ROT)
            _log(f"Descend target Z={_target[2]:.3f}")
            _go(DESCEND_PICK)
        return True

    # ── DESCEND_PICK ─────────────────────────────────────────
    if _state == DESCEND_PICK:
        _rmp_step()
        _frame += 1
        if _converged(_target):
            _grip(GRIPPER_CLOSE)
            _log(f"Grasping at EE={np.round(_ee(), 3).tolist()}")
            _go(CLOSE_GRIPPER)
        return True

    # ── CLOSE_GRIPPER ────────────────────────────────────────
    if _state == CLOSE_GRIPPER:
        _rmp_step()
        _frame += 1
        if _frame >= GRIPPER_WAIT:
            _target = _cube_pos.copy()
            _target[2] += APPROACH_HEIGHT
            _aim(_target, GRASP_ROT)
            _go(LIFT)
        return True

    # ── LIFT ─────────────────────────────────────────────────
    if _state == LIFT:
        _rmp_step()
        _frame += 1
        if _converged(_target):
            _target = _place_pos.copy()
            _target[2] += APPROACH_HEIGHT
            _aim(_target, GRASP_ROT)
            _go(APPROACH_PLACE)
        return True

    # ── APPROACH_PLACE ───────────────────────────────────────
    if _state == APPROACH_PLACE:
        _rmp_step()
        _frame += 1
        if _converged(_target):
            _target = _place_pos.copy()
            _target[2] += GRASP_Z_OFFSET
            _aim(_target, GRASP_ROT)
            _go(DESCEND_PLACE)
        return True

    # ── DESCEND_PLACE ────────────────────────────────────────
    if _state == DESCEND_PLACE:
        _rmp_step()
        _frame += 1
        if _converged(_target):
            _grip(GRIPPER_OPEN)
            _go(RELEASE)
        return True

    # ── RELEASE ──────────────────────────────────────────────
    if _state == RELEASE:
        _rmp_step()
        _frame += 1
        if _frame >= GRIPPER_WAIT:
            _target = _place_pos.copy()
            _target[2] += APPROACH_HEIGHT
            _aim(_target, GRASP_ROT)
            _go(RETREAT)
        return True

    # ── RETREAT ──────────────────────────────────────────────
    if _state == RETREAT:
        _rmp_step()
        _frame += 1
        if _converged(_target):
            _log("=== PICK AND PLACE COMPLETE ===")
            _go(DONE)
        return True

    # ── DONE ─────────────────────────────────────────────────
    if _state == DONE:
        _rmp_step()
        return True

    return True
