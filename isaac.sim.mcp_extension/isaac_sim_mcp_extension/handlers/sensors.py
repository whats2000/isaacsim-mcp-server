"""Sensor creation and data capture command handlers."""

import base64
import os


def register(registry, adapter):
    registry["sensors.create_camera"] = lambda **p: create_camera(adapter, **p)
    registry["sensors.capture_image"] = lambda **p: capture_image(adapter, **p)
    registry["sensors.create_lidar"] = lambda **p: create_lidar(adapter, **p)
    registry["sensors.get_point_cloud"] = lambda **p: get_point_cloud(adapter, **p)


def create_camera(adapter, prim_path="/World/Camera", position=None, rotation=None, resolution=None):
    try:
        res = tuple(resolution) if resolution else (1280, 720)
        cam = adapter.create_camera(prim_path, resolution=res)
        if position or rotation:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation)
        return {"status": "success", "message": f"Camera created at {prim_path}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def capture_image(adapter, prim_path="/World/Camera", output_path=None):
    try:
        image_data = adapter.capture_camera_image(prim_path)
        if output_path:
            import numpy as np
            from PIL import Image
            img = Image.fromarray(image_data)
            img.save(output_path)
            return {"status": "success", "message": f"Image saved to {output_path}", "output_path": output_path}
        return {"status": "success", "message": "Image captured", "shape": list(image_data.shape) if hasattr(image_data, "shape") else None}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_lidar(adapter, prim_path="/World/Lidar", position=None, rotation=None, config=None):
    try:
        adapter.create_lidar(prim_path, config=config)
        if position or rotation:
            adapter.set_prim_transform(prim_path, position=position, rotation=rotation)
        return {"status": "success", "message": f"Lidar created at {prim_path}", "prim_path": prim_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_point_cloud(adapter, prim_path="/World/Lidar"):
    try:
        pc = adapter.get_lidar_point_cloud(prim_path)
        point_count = len(pc) if pc is not None else 0
        return {"status": "success", "message": f"Got {point_count} points", "point_count": point_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}
