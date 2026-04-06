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

"""Action Graph command handlers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..adapters.base import IsaacAdapterBase


def register(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    registry["graphs.create_action_graph"] = lambda **p: create_action_graph(adapter, **p)


def create_action_graph(
    adapter: IsaacAdapterBase,
    graph_path: str = "/World/ActionGraph",
    nodes: Optional[List[Dict[str, str]]] = None,
    connections: Optional[List[List[str]]] = None,
    values: Optional[List[Dict[str, object]]] = None,
    evaluator: str = "push",
) -> Dict[str, Any]:
    """Create an OmniGraph Action Graph with nodes, connections and values."""
    try:
        import omni.graph.core as og

        # Build og.Controller.Keys-based edit descriptor
        edit_kwargs: Dict[str, Any] = {
            "graph_path": graph_path,
            "evaluator_name": evaluator,
        }

        # Convert node dicts to tuples expected by og.Controller
        og_nodes = []
        if nodes:
            for n in nodes:
                node_path = n.get("path", "")
                node_type = n.get("type", "")
                if not node_path or not node_type:
                    return {"status": "error", "message": f"Each node needs 'path' and 'type', got: {n}"}
                og_nodes.append((node_type, node_path))

        # Convert connection pairs: resolve relative paths to absolute graph paths
        og_connections = []
        if connections:
            for conn in connections:
                if len(conn) != 2:
                    return {"status": "error", "message": f"Each connection must be [source, target], got: {conn}"}
                src = f"{graph_path}/{conn[0]}" if not conn[0].startswith("/") else conn[0]
                tgt = f"{graph_path}/{conn[1]}" if not conn[1].startswith("/") else conn[1]
                og_connections.append((src, tgt))

        # Convert value dicts: resolve relative attr paths
        og_values = []
        if values:
            for v in values:
                attr = v.get("attr", "")
                val = v.get("value")
                if not attr:
                    return {"status": "error", "message": f"Each value entry needs 'attr', got: {v}"}
                full_attr = f"{graph_path}/{attr}" if not attr.startswith("/") else attr
                og_values.append((full_attr, val))

        # Build and execute the graph edit
        keys = og.Controller.Keys
        edit_spec = {keys.CREATE_NODES: og_nodes}
        if og_connections:
            edit_spec[keys.CONNECT] = og_connections
        if og_values:
            edit_spec[keys.SET_VALUES] = og_values

        (graph, new_nodes, _, _) = og.Controller.edit(
            edit_kwargs,
            edit_spec,
        )

        created_node_paths = [n.get_prim_path() for n in new_nodes] if new_nodes else []

        return {
            "status": "success",
            "message": f"Action Graph created at {graph_path}",
            "graph_path": graph_path,
            "node_count": len(created_node_paths),
            "nodes": created_node_paths,
        }
    except Exception as e:
        import traceback

        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
