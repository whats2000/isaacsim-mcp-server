"""Material creation and binding command handlers."""


def register(registry, adapter):
    registry["materials.create"] = lambda **p: create(adapter, **p)
    registry["materials.apply"] = lambda **p: apply_material(adapter, **p)


def create(adapter, material_type="pbr", prim_path=None, color=None, roughness=0.5, metallic=0.0,
           static_friction=0.5, dynamic_friction=0.5, restitution=0.0):
    try:
        if not prim_path:
            stage = adapter.get_stage()
            count = len(list(stage.TraverseAll()))
            prim_path = f"/World/Material_{count}"
        if material_type == "pbr":
            adapter.create_pbr_material(prim_path, color=color, roughness=roughness, metallic=metallic)
        elif material_type == "physics":
            adapter.create_physics_material(prim_path, static_friction=static_friction,
                                            dynamic_friction=dynamic_friction, restitution=restitution)
        else:
            return {"status": "error", "message": f"Unknown material type: {material_type}. Options: pbr, physics"}
        return {"status": "success", "message": f"Created {material_type} material", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def apply_material(adapter, material_path=None, target_prim_path=None):
    try:
        if not material_path or not target_prim_path:
            return {"status": "error", "message": "material_path and target_prim_path are required"}
        adapter.apply_material(material_path, target_prim_path)
        return {"status": "success", "message": f"Applied {material_path} to {target_prim_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
