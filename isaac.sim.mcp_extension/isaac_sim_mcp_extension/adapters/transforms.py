# MIT License
#
# Copyright (c) 2023-2025 omni-mcp
# Copyright (c) 2026 whats2000
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Reading and writing prim transforms.

A prim's rotation may be authored as ``xformOp:orient`` (a quaternion) or
``xformOp:rotateXYZ`` (euler degrees), and both adapters previously only ever
wrote the euler op. On a prim that already carried an ``orient`` -- which is
what this extension's own object and camera creation produces, and what
referenced assets and robots ship -- the requested rotation was *appended*
rather than replacing anything, so it composed with the existing orientation
and landed after ``xformOp:scale`` in the op order. Measured on a Franka-style
prim carrying ``orient``=90 deg and ``scale``=(1,2,1): asking for 45 deg
produced 135 deg and a shear of 1.5.

Writing into whichever op the prim actually uses fixes both, because the
existing op already sits ahead of ``scale``. When a prim has neither op, the
new rotate op is *inserted* before ``scale`` rather than appended, so scale
stays the outermost operation and cannot shear the rotation.

Euler values are XYZ order in degrees, matching ``AddRotateXYZOp``, so prims
that already use ``rotateXYZ`` behave exactly as before.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

ROTATE_OPS = (
    "xformOp:rotateXYZ",
    "xformOp:rotateXZY",
    "xformOp:rotateYXZ",
    "xformOp:rotateYZX",
    "xformOp:rotateZXY",
    "xformOp:rotateZYX",
)


def _euler_to_quat(rotation: Sequence[float]):
    """XYZ euler degrees -> quaternion, matching rotateXYZ semantics."""
    from pxr import Gf

    rx, ry, rz = (float(v) for v in rotation)
    m = (
        Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), rx))
        * Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), ry))
        * Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), rz))
    )
    return m.ExtractRotationQuat()


def _set_orient(op, rotation: Sequence[float]) -> None:
    """Write euler degrees into a quaternion op at the op's own precision."""
    from pxr import Gf, UsdGeom

    quat = _euler_to_quat(rotation)
    precision = op.GetPrecision()
    if precision == UsdGeom.XformOp.PrecisionDouble:
        op.Set(Gf.Quatd(quat))
    elif precision == UsdGeom.XformOp.PrecisionHalf:
        op.Set(Gf.Quath(Gf.Quatf(quat)))
    else:
        op.Set(Gf.Quatf(quat))


def _insert_before_scale(xformable, op) -> None:
    """Move ``op`` ahead of xformOp:scale so scale stays outermost."""
    ops = list(xformable.GetOrderedXformOps())
    names = [o.GetName() for o in ops]
    if "xformOp:scale" not in names:
        return
    rest = [o for o in ops if o.GetName() != op.GetName()]
    index = [o.GetName() for o in rest].index("xformOp:scale")
    rest.insert(index, op)
    xformable.SetXformOpOrder(rest, xformable.GetResetXformStack())


def set_transform(
    xformable,
    position: Optional[Sequence[float]] = None,
    rotation: Optional[Sequence[float]] = None,
    scale: Optional[Sequence[float]] = None,
) -> None:
    """Set the requested components, leaving the others untouched.

    Only writes an op the caller asked for: clearing the whole op order (the
    original behaviour) silently reset every axis the caller did not pass.
    """
    from pxr import Gf, UsdGeom

    existing = {op.GetName(): op for op in xformable.GetOrderedXformOps()}

    if position is not None:
        op = existing.get("xformOp:translate") or xformable.AddTranslateOp(precision=UsdGeom.XformOp.PrecisionDouble)
        op.Set(Gf.Vec3d(*position))

    if rotation is not None:
        orient = existing.get("xformOp:orient")
        euler_name = next((n for n in ROTATE_OPS if n in existing), None)
        if orient is not None:
            _set_orient(orient, rotation)
            # A prim carrying both would otherwise compose the two.
            if euler_name is not None:
                existing[euler_name].Set(Gf.Vec3d(0, 0, 0))
        elif euler_name is not None:
            existing[euler_name].Set(Gf.Vec3d(*rotation))
        else:
            op = xformable.AddRotateXYZOp(precision=UsdGeom.XformOp.PrecisionDouble)
            op.Set(Gf.Vec3d(*rotation))
            _insert_before_scale(xformable, op)

    if scale is not None:
        op = existing.get("xformOp:scale") or xformable.AddScaleOp(precision=UsdGeom.XformOp.PrecisionDouble)
        op.Set(Gf.Vec3d(*scale))


def world_translation(xformable) -> Optional[list]:
    """World-space translation of a prim, or None when it cannot be computed."""
    from pxr import Usd

    try:
        matrix = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        t = matrix.ExtractTranslation()
        return [float(t[0]), float(t[1]), float(t[2])]
    except Exception:
        return None


def read_transform(xformable) -> Dict[str, Any]:
    """Return position (both frames), rotation (XYZ euler degrees) and scale.

    There is deliberately no bare ``position``. It used to hold the *local*
    (parent-relative) pose with nothing saying so, and for a prim under a
    transformed parent that number is not where the object is: a child at local
    (0.25, 0, 0) under a parent at (1, 2, 0.5) reported [0.25, 0, 0] while
    ``actual_size`` in the same response was world-space. Robot links are where
    it bit -- ``/World/Franka/fr3_hand_tcp`` -- because Isaac's FR3 is a flat
    hierarchy rooted at the articulation, so a robot at the default origin makes
    the two frames coincide and the tool look correct.

    Naming one of them ``position`` and the other ``position_world`` would keep
    the trap: the unqualified name reads as the default and the qualified one as
    a special case. Both are named, so a caller has to choose.

    ``rotation`` and ``scale`` stay unqualified because they are local by
    definition -- they are the values ``transform_object`` writes back, in the
    same convention. Only position has a world reading worth deriving.

    The rotation is taken from the orthonormalized local matrix, so it is
    correct whichever op authored it, and scale cannot corrupt it -- reading
    the angle off a matrix that still carries scale is exactly the trap that
    makes a scaled prim report a nonsense rotation.
    """
    from pxr import Gf

    matrix = xformable.GetLocalTransformation()
    translation = matrix.ExtractTranslation()

    rotation_matrix = Gf.Matrix4d(matrix)
    rotation_matrix.Orthonormalize()
    # Decompose returns the angles about the axes in reverse application order.
    rz, ry, rx = rotation_matrix.ExtractRotation().Decompose(Gf.Vec3d(0, 0, 1), Gf.Vec3d(0, 1, 0), Gf.Vec3d(1, 0, 0))

    scale = [Gf.Vec3d(matrix[i][0], matrix[i][1], matrix[i][2]).GetLength() for i in range(3)]

    result: Dict[str, Any] = {
        "position_local": [translation[0], translation[1], translation[2]],
        "rotation": [round(float(rx), 6), round(float(ry), 6), round(float(rz), 6)],
        "rotation_units": "degrees",
        "scale": [round(float(v), 6) for v in scale],
    }

    world = world_translation(xformable)
    if world is not None:
        result["position_world"] = world
        result["position_world_source"] = "usd"
    else:
        # Never fall back to the local value under a world name -- that is the
        # #39 bug restated. Say the reading is missing instead.
        result["position_world_warning"] = (
            "The world transform for this prim could not be computed, so only position_local "
            "(parent-relative) is reported. Do not treat position_local as a world coordinate."
        )
    return result


def look_at_euler(eye, target, up=(0.0, 0.0, 1.0)):
    """XYZ euler degrees that aim a camera at ``target`` from ``eye``.

    Cameras look down their local -Z, and this extension's own creation path
    gives them a non-identity ``orient``, so aiming one by hand meant composing
    that built-in orientation with euler angles worked out by trigonometry --
    three guess-and-check attempts in practice, and a shot of the sky when the
    arithmetic was right but the composition was not.

    Returned in the same XYZ-degrees convention ``set_transform`` accepts and
    ``read_transform`` reports, so a camera aimed this way reads back
    consistently.

    Returns ``None`` when there is no direction to derive -- eye and target
    coincident -- so the caller can leave the orientation alone rather than
    author a garbage one.
    """
    from pxr import Gf

    eye_v = Gf.Vec3d(*(float(v) for v in eye))
    target_v = Gf.Vec3d(*(float(v) for v in target))
    direction = target_v - eye_v
    if direction.GetLength() < 1e-9:
        return None

    up_v = Gf.Vec3d(*(float(v) for v in up))
    # Looking straight along the up axis leaves the roll undefined and SetLookAt
    # degenerates; swap in an axis that is not parallel to the view direction.
    if abs(Gf.Vec3d(direction).GetNormalized() * up_v.GetNormalized()) > 0.999:
        up_v = Gf.Vec3d(0.0, 1.0, 0.0) if abs(up_v[2]) > 0.5 else Gf.Vec3d(0.0, 0.0, 1.0)

    world = Gf.Matrix4d().SetLookAt(eye_v, target_v, up_v).GetInverse()
    world.Orthonormalize()
    rz, ry, rx = world.ExtractRotation().Decompose(Gf.Vec3d(0, 0, 1), Gf.Vec3d(0, 1, 0), Gf.Vec3d(1, 0, 0))
    return [round(float(rx), 6), round(float(ry), 6), round(float(rz), 6)]
