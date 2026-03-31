"""Isaac Sim MCP Server — entry point.

Registers all tools from tools/ submodules and starts the FastMCP server.
"""

import logging
from mcp.server.fastmcp import FastMCP
from isaac_mcp.connection import get_isaac_connection, reset_isaac_connection
from isaac_mcp.tools import register_all_tools
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("IsaacMCPServer")


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle."""
    try:
        logger.info("IsaacMCP server starting up")
        try:
            get_isaac_connection()
            logger.info("Successfully connected to Isaac on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Isaac on startup: {e}")
        yield {}
    finally:
        reset_isaac_connection()
        logger.info("IsaacMCP server shut down")


mcp = FastMCP(
    "IsaacSimMCP",
    description="Isaac Sim integration through the Model Context Protocol",
    lifespan=server_lifespan,
)

register_all_tools(mcp, get_isaac_connection)


@mcp.prompt()
def asset_creation_strategy() -> str:
    """Defines the preferred strategy for creating assets in Isaac Sim"""
    return """
    0. Before anything, always check the scene with get_scene_info() to verify connection and get the assets root path.
    1. If the scene is empty, create a physics scene with create_physics_scene().
    2. If execute_script fails due to communication error, retry up to 3 times.
    3. Use create_robot() as the first attempt for robot creation before falling back to execute_script().
    4. Use create_light() to add lighting to the scene.
    5. Use create_object() for primitive shapes, create_material() + apply_material() for appearance.
    6. Use play_simulation() / stop_simulation() to control the simulation lifecycle.
    """


def main():
    mcp.run()


if __name__ == "__main__":
    main()
