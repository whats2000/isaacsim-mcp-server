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

"""TCP socket server for Isaac Sim MCP — connection and dispatch logic."""

from __future__ import annotations

import json
import socket
import threading
import time
import traceback
from typing import Callable, Dict, Any


class SocketServer:
    """Manages a TCP socket server that accepts JSON commands and returns responses.

    Parameters
    ----------
    host:
        Hostname or IP address to bind to.
    port:
        Port number to listen on.
    command_handler:
        Callable invoked with the parsed command dict; must return a response dict.
    """

    def __init__(
        self,
        host: str,
        port: int,
        command_handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        self.host = host
        self.port = port
        self._command_handler = command_handler
        self.running: bool = False
        self._socket: socket.socket | None = None
        self._server_thread: threading.Thread | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Bind the socket and start the background accept loop."""
        if self.running:
            return
        self.running = True
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.host, self.port))
            self._socket.listen(1)
            self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self._server_thread.start()
            print(f"Isaac Sim MCP server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to start server: {e}")
            self.stop()

    def stop(self) -> None:
        """Signal the server to stop and close the socket."""
        self.running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
        self._server_thread = None
        print("Isaac Sim MCP server stopped")

    # ── Connection handling ────────────────────────────────────────────────────

    def _server_loop(self) -> None:
        self._socket.settimeout(1.0)
        while self.running:
            try:
                client, address = self._socket.accept()
                print(f"Connected to client: {address}")
                threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
                    time.sleep(0.5)

    def _handle_client(self, client: socket.socket) -> None:
        client.settimeout(None)
        buffer = b""
        try:
            while self.running:
                data = client.recv(16384)
                if not data:
                    break
                buffer += data
                try:
                    command = json.loads(buffer.decode("utf-8"))
                    buffer = b""
                    self._dispatch_command(client, command)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            print(f"Error in client handler: {e}")
        finally:
            client.close()

    def _dispatch_command(self, client: socket.socket, command: Dict[str, Any]) -> None:
        async def execute_wrapper() -> None:
            try:
                response = self._command_handler(command)
                response_json = json.dumps(response)
                try:
                    client.sendall(response_json.encode("utf-8"))
                except Exception:
                    print("Failed to send response — client disconnected")
            except Exception as e:
                traceback.print_exc()
                try:
                    client.sendall(
                        json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                    )
                except Exception:
                    pass

        from omni.kit.async_engine import run_coroutine
        run_coroutine(execute_wrapper())
