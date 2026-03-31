"""Lighting command handlers."""


def register(registry, adapter):
    registry["lighting.create"] = lambda **p: create(adapter, **p)
    registry["lighting.modify"] = lambda **p: modify(adapter, **p)


def create(adapter, light_type="DistantLight", position=None, intensity=1000.0, color=None, rotation=None, prim_path=None):
    try:
        if not prim_path:
            stage = adapter.get_stage()
            count = len(list(stage.TraverseAll()))
            prim_path = f"/World/{light_type}_{count}"
        adapter.create_light(light_type, prim_path, intensity=intensity, color=color, position=position, rotation=rotation)
        return {"status": "success", "message": f"Created {light_type}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def modify(adapter, prim_path=None, intensity=None, color=None):
    try:
        if not prim_path:
            return {"status": "error", "message": "prim_path is required"}
        adapter.modify_light(prim_path, intensity=intensity, color=color)
        return {"status": "success", "message": f"Modified light at {prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
