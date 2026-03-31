"""Scene management command handlers."""

import traceback


def register(registry, adapter):
    registry["scene.get_info"] = lambda **p: get_info(adapter, **p)
    registry["scene.create_physics"] = lambda **p: create_physics(adapter, **p)
    registry["scene.clear"] = lambda **p: clear(adapter, **p)
    registry["scene.list_prims"] = lambda **p: list_prims(adapter, **p)
    registry["scene.get_prim_info"] = lambda **p: get_prim_info(adapter, **p)


def get_info(adapter):
    try:
        stage = adapter.get_stage()
        assets_root = adapter.get_assets_root_path()
        prim_count = len(list(stage.TraverseAll()))
        stage_path = stage.GetRootLayer().realPath
        return {
            "status": "success",
            "message": "pong",
            "assets_root_path": assets_root,
            "stage_path": stage_path,
            "prim_count": prim_count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_physics(adapter, gravity=None, scene_name="PhysicsScene"):
    try:
        scene_path = adapter.create_physics_scene(gravity=gravity, scene_name=scene_name)
        # Create ground plane
        import omni.kit.commands
        floor_path = "/World/groundPlane"
        omni.kit.commands.execute("CreatePrim", prim_path=floor_path, prim_type="Plane")
        return {"status": "success", "message": f"Physics scene created at {scene_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clear(adapter, keep_physics=False):
    try:
        stage = adapter.get_stage()
        root = stage.GetPrimAtPath("/World")
        if root.IsValid():
            children = root.GetAllChildren()
            for child in children:
                path = str(child.GetPath())
                if keep_physics and "Physics" in path:
                    continue
                adapter.delete_prim(path)
        return {"status": "success", "message": "Scene cleared"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_prims(adapter, root_path="/", prim_type=None):
    try:
        prims = adapter.list_prims(root_path=root_path, prim_type=prim_type)
        return {"status": "success", "prims": prims}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_prim_info(adapter, prim_path="/"):
    try:
        info = adapter.get_prim_info(prim_path)
        return {"status": "success", **info}
    except Exception as e:
        return {"status": "error", "message": str(e)}
