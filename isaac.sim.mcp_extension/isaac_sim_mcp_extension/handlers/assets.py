"""Asset import and loading command handlers."""

from isaac_sim_mcp_extension.gen3d import Beaver3d
from isaac_sim_mcp_extension.usd import USDLoader, USDSearch3d


def register(registry, adapter):
    registry["assets.import_urdf"] = lambda **p: import_urdf(adapter, **p)
    registry["assets.load_usd"] = lambda **p: load_usd(adapter, **p)
    registry["assets.search_usd"] = lambda **p: search_usd(adapter, **p)
    registry["assets.generate_3d"] = lambda **p: generate_3d(adapter, **p)


def import_urdf(adapter, urdf_path=None, prim_path="/World/robot", position=None):
    try:
        if not urdf_path:
            return {"status": "error", "message": "urdf_path is required"}
        result = adapter.import_urdf(urdf_path, prim_path=prim_path)
        if position:
            adapter.set_prim_transform(prim_path, position=position)
        return {"status": "success", "message": f"Imported URDF from {urdf_path}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def load_usd(adapter, usd_url=None, prim_path="/World/my_usd", position=None, scale=None):
    try:
        if not usd_url:
            return {"status": "error", "message": "usd_url is required"}
        loader = USDLoader()
        result_path = loader.load_usd_from_url(url_path=usd_url, target_path=prim_path, location=position, scale=scale)
        return {"status": "success", "message": f"Loaded USD from {usd_url}", "prim_path": result_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_usd(adapter, text_prompt=None, target_path="/World/my_usd", position=None, scale=None):
    try:
        if not text_prompt:
            return {"status": "error", "message": "text_prompt is required"}
        searcher = USDSearch3d()
        url = searcher.search(text_prompt)
        loader = USDLoader()
        prim_path = loader.load_usd_from_url(url_path=url, target_path=target_path)
        return {"status": "success", "message": f"Found and loaded USD for '{text_prompt}'", "prim_path": prim_path, "url": url}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def generate_3d(adapter, text_prompt=None, image_url=None, position=None, scale=None):
    try:
        if not text_prompt and not image_url:
            return {"status": "error", "message": "Either text_prompt or image_url is required"}
        beaver = Beaver3d()
        if image_url:
            task_id = beaver.generate_3d_from_image(image_url)
        else:
            task_id = beaver.generate_3d_from_text(text_prompt)

        def on_complete(task_id, status, result_path):
            loader = USDLoader()
            loader.load_usd_model(task_id=task_id)
            try:
                loader.load_texture_and_create_material(task_id=task_id)
                loader.bind_texture_to_model()
            except Exception:
                pass
            if position or scale:
                loader.transform(position=position or (0, 0, 50), scale=scale or (10, 10, 10))

        from omni.kit.async_engine import run_coroutine
        run_coroutine(beaver.monitor_task_status_async(task_id, on_complete_callback=on_complete))
        return {"status": "success", "message": f"3D generation started", "task_id": task_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}
