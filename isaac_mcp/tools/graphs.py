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

"""Action Graph MCP tools."""

import json
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from isaac_mcp.connection import IsaacConnection


def register_tools(mcp: FastMCP, get_connection: "Callable[[], IsaacConnection]") -> None:

    @mcp.tool("create_action_graph")
    def create_action_graph(
        graph_path: str = "/World/ActionGraph",
        nodes: Optional[List[Dict[str, str]]] = None,
        connections: Optional[List[List[str]]] = None,
        values: Optional[List[Dict[str, object]]] = None,
        evaluator: str = "push",
    ) -> str:
        """Create and wire an OmniGraph Action Graph.

        Builds a complete Action Graph with nodes, connections and attribute values
        using og.Controller.edit(). This is the programmatic equivalent of creating
        an Action Graph in the visual editor.

        Args:
            graph_path: USD prim path for the graph (default "/World/ActionGraph").
            nodes: List of node definitions. Each dict has:
                - "path": Node path relative to graph (e.g. "OnPlaybackTick")
                - "type": OmniGraph node type (e.g. "omni.graph.action.OnPlaybackTick")
            connections: List of [source_attr, target_attr] pairs for wiring nodes.
                Each attr is "NodePath.outputs:attrName" or "NodePath.inputs:attrName".
            values: List of attribute value overrides. Each dict has:
                - "attr": Full attribute path (e.g. "ScriptNode.inputs:script")
                - "value": The value to set
            evaluator: Graph evaluator type (default "push").

        Example:
            create_action_graph(
                graph_path="/World/ActionGraph",
                nodes=[
                    {"path": "OnPlaybackTick", "type": "omni.graph.action.OnPlaybackTick"},
                    {"path": "ScriptNode", "type": "omni.graph.scriptnode.ScriptNode"},
                ],
                connections=[
                    ["OnPlaybackTick.outputs:tick", "ScriptNode.inputs:execIn"]
                ],
                values=[
                    {"attr": "ScriptNode.inputs:script", "value": "print('hello')"}
                ]
            )
        """
        try:
            conn = get_connection()
            params: Dict[str, object] = {"graph_path": graph_path, "evaluator": evaluator}
            if nodes is not None:
                params["nodes"] = nodes
            if connections is not None:
                params["connections"] = connections
            if values is not None:
                params["values"] = values
            result = conn.send_command("graphs.create_action_graph", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
