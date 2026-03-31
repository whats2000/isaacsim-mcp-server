"""Robot creation and control command handlers."""

import numpy as np


ROBOT_LIBRARY = {
    "franka": {"asset_path": "/Isaac/Robots/Franka/franka_alt_fingers.usd", "description": "Franka Emika Panda manipulator"},
    "jetbot": {"asset_path": "/Isaac/Robots/Jetbot/jetbot.usd", "description": "NVIDIA JetBot mobile robot"},
    "carter": {"asset_path": "/Isaac/Robots/Carter/carter.usd", "description": "Carter delivery robot"},
    "g1": {"asset_path": "/Isaac/Robots/Unitree/G1/g1.usd", "description": "Unitree G1 humanoid robot"},
    "go1": {"asset_path": "/Isaac/Robots/Unitree/Go1/go1.usd", "description": "Unitree Go1 quadruped robot"},
}


def register(registry, adapter):
    registry["robots.create"] = lambda **p: create(adapter, **p)
    registry["robots.list"] = lambda **p: list_robots(adapter, **p)
    registry["robots.get_info"] = lambda **p: get_info(adapter, **p)
    registry["robots.set_joints"] = lambda **p: set_joints(adapter, **p)
    registry["robots.get_joints"] = lambda **p: get_joints(adapter, **p)


def create(adapter, robot_type="franka", position=None, name=None):
    try:
        robot_type_lower = robot_type.lower()
        if robot_type_lower not in ROBOT_LIBRARY:
            return {"status": "error", "message": f"Unknown robot: {robot_type}. Options: {list(ROBOT_LIBRARY.keys())}"}
        assets_root = adapter.get_assets_root_path()
        asset_path = assets_root + ROBOT_LIBRARY[robot_type_lower]["asset_path"]
        prim_name = name or robot_type_lower.capitalize()
        prim_path = f"/{prim_name}"
        adapter.add_reference_to_stage(asset_path, prim_path)
        if position:
            xform = adapter.create_xform_prim(prim_path)
            xform.set_world_pose(position=np.array(position))
        return {"status": "success", "message": f"Created {robot_type} robot", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_robots(adapter):
    return {"status": "success", "robots": ROBOT_LIBRARY}


def get_info(adapter, prim_path=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        info = adapter.get_robot_joint_info(prim_path)
        return {"status": "success", **info}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_joints(adapter, prim_path=None, joint_positions=None, joint_indices=None):
    try:
        if not prim_path or joint_positions is None:
            return {"status": "error", "message": "prim_path and joint_positions are required"}
        adapter.set_joint_positions(prim_path, joint_positions, joint_indices)
        return {"status": "success", "message": f"Set joint positions on {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_joints(adapter, prim_path=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        positions = adapter.get_joint_positions(prim_path)
        return {"status": "success", "joint_positions": positions}
    except Exception as e:
        return {"status": "error", "message": str(e)}
