# MIT License
#
# Copyright (c) 2023-2025 omni-mcp
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

"""Command handler modules for the Isaac Sim extension."""
from __future__ import annotations

from typing import Any, Dict

from ..adapters.base import IsaacAdapterBase


def register_all_handlers(registry: Dict[str, Any], adapter: IsaacAdapterBase) -> None:
    """Register all command handlers from submodules.

    Args:
        registry: Dict mapping command type strings to handler callables.
        adapter: IsaacAdapterBase instance for version-specific API calls.
    """
    from . import scene, objects, lighting, robots, sensors, materials, assets, simulation

    for module in [scene, objects, lighting, robots, sensors, materials, assets, simulation]:
        module.register(registry, adapter)
