"""Simulation control command handlers."""


def register(registry, adapter):
    registry["simulation.play"] = lambda **p: play(adapter, **p)
    registry["simulation.pause"] = lambda **p: pause(adapter, **p)
    registry["simulation.stop"] = lambda **p: stop(adapter, **p)
    registry["simulation.step"] = lambda **p: step(adapter, **p)
    registry["simulation.set_physics"] = lambda **p: set_physics(adapter, **p)
    registry["simulation.execute_script"] = lambda **p: execute_script(adapter, **p)


def play(adapter):
    try:
        adapter.play()
        return {"status": "success", "message": "Simulation started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def pause(adapter):
    try:
        adapter.pause()
        return {"status": "success", "message": "Simulation paused"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def stop(adapter):
    try:
        adapter.stop()
        return {"status": "success", "message": "Simulation stopped"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def step(adapter, num_steps=1):
    try:
        adapter.step(num_steps=num_steps)
        return {"status": "success", "message": f"Stepped {num_steps} frames"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_physics(adapter, gravity=None, time_step=None, gpu_enabled=None):
    try:
        # Physics params are set via the PhysicsContext on the World
        # For now, gravity is the most common parameter
        if gravity is not None:
            adapter.create_physics_scene(gravity=gravity)
        return {"status": "success", "message": "Physics parameters updated"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_script(adapter, code=None):
    try:
        if not code:
            return {"status": "error", "message": "code is required"}
        result = adapter.execute_script(code)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
