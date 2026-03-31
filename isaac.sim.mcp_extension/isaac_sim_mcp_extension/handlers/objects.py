"""Object creation and manipulation command handlers."""


def register(registry, adapter):
    registry["objects.create"] = lambda **p: create(adapter, **p)
    registry["objects.delete"] = lambda **p: delete(adapter, **p)
    registry["objects.transform"] = lambda **p: transform(adapter, **p)
    registry["objects.clone"] = lambda **p: clone(adapter, **p)


def create(adapter, object_type="Cube", position=None, rotation=None, scale=None, color=None, physics_enabled=False, prim_path=None):
    try:
        if not prim_path:
            stage = adapter.get_stage()
            count = len(list(stage.TraverseAll()))
            prim_path = f"/World/{object_type}_{count}"
        prim = adapter.create_prim(prim_path, prim_type=object_type)
        if position or rotation or scale:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation, scale=scale)
        return {"status": "success", "message": f"Created {object_type}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete(adapter, prim_path=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.delete_prim(prim_path)
        return {"status": "success", "message": f"Deleted {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def transform(adapter, prim_path=None, position=None, rotation=None, scale=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.set_prim_transform(prim_path, position=position, rotation=rotation, scale=scale)
        return {"status": "success", "message": f"Transformed {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clone(adapter, source_path=None, target_path=None, position=None):
    try:
        if not source_path or not target_path:
            return {"status": "error", "message": "source_path and target_path are required"}
        import omni.kit.commands
        omni.kit.commands.execute("CopyPrim", path_from=source_path, path_to=target_path)
        if position:
            adapter.set_prim_transform(target_path, position=position)
        return {"status": "success", "message": f"Cloned {source_path} to {target_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
