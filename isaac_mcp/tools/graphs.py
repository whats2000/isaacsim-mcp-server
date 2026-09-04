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
        evaluator: str = "execution",
        script_file: Optional[str] = None,
        inline_script: Optional[str] = None,
    ) -> str:
        """Create and wire an OmniGraph Action Graph.

        Args:
            graph_path: USD prim path for the graph (default "/World/ActionGraph").
            nodes: [{"path": <path relative to graph>, "type": <node type>}],
                e.g. {"path": "OnPlaybackTick", "type": "omni.graph.action.OnPlaybackTick"}.
            connections: [source_attr, target_attr] pairs, each written
                "NodePath.outputs:attrName" or "NodePath.inputs:attrName".
            values: [{"attr": "ScriptNode.inputs:script", "value": ...}] overrides.
            evaluator: Graph evaluator (default "execution", what Action Graphs
                use). "push" evaluates every app update regardless of the
                timeline, so an OnPlaybackTick ScriptNode keeps running while
                the simulation is stopped.
            script_file: Path to a local Python script. Auto-creates and wires
                OnPlaybackTick → ScriptNode and attaches the file; `nodes` and
                `connections` are ignored. Recommended for anything you will
                iterate on — edit the file, then reload_script.
            inline_script: Inline Python instead of a file (must define
                setup(db)/compute(db)). Same auto-wiring. For small static
                graphs only: editing it needs edit_action_graph, not
                reload_script.

        Example (recommended for iteration):
            create_action_graph(script_file="/path/to/controller.py")
        """
        try:
            conn = get_connection()
            params: Dict[str, object] = {"graph_path": graph_path, "evaluator": evaluator}
            if script_file is not None:
                params["script_file"] = script_file
            elif inline_script is not None:
                params["inline_script"] = inline_script
            else:
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

    @mcp.tool("edit_action_graph")
    def edit_action_graph(
        graph_path: str = "/World/ActionGraph",
        values: Optional[List[Dict[str, object]]] = None,
        connections: Optional[List[List[str]]] = None,
    ) -> str:
        """Edit an existing Action Graph: set attribute values or add connections.

        Use this to update a ScriptNode's script (inline or file path), change
        attribute values, or add connections on an already-created graph.

        For a ScriptNode backed by a file, set usePath alongside the path:
            values=[
                {"attr": "ScriptNode.inputs:usePath",    "value": true},
                {"attr": "ScriptNode.inputs:scriptPath", "value": "/path/to/script.py"}
            ]
        For an inline script, set usePath false and write "inputs:script" instead.

        Args:
            graph_path: USD prim path of the existing graph (default "/World/ActionGraph").
            values: Attribute overrides — {"attr": "<Node>.inputs:<name>", "value": ...}.
            connections: List of [source_attr, target_attr] pairs to add.
        """
        try:
            conn = get_connection()
            params: Dict[str, object] = {"graph_path": graph_path}
            if values is not None:
                params["values"] = values
            if connections is not None:
                params["connections"] = connections
            result = conn.send_command("graphs.edit_action_graph", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
