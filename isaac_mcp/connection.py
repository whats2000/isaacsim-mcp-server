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

"""Socket connection to the Isaac Sim extension server."""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("IsaacMCPServer")

DEFAULT_PORT = 8766


@dataclass
class IsaacConnection:
    """Manages a persistent TCP socket connection to the Isaac Sim extension."""

    host: str = "localhost"
    port: int = 0

    def __post_init__(self):
        if self.port == 0:
            self.port = int(os.environ.get("ISAAC_MCP_PORT", DEFAULT_PORT))

    sock: Optional[socket.socket] = field(default=None, repr=False)

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Isaac at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Isaac: {e}")
            self.sock = None
            return False

    def disconnect(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            finally:
                self.sock = None

    def receive_full_response(self, sock: socket.socket, buffer_size: int = 16384) -> bytes:
        chunks = []
        sock.settimeout(300.0)
        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break
                    chunks.append(chunk)
                    try:
                        data = b"".join(chunks)
                        json.loads(data.decode("utf-8"))
                        return data
                    except json.JSONDecodeError:
                        continue
                except socket.timeout:
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError):
                    raise
        except socket.timeout:
            pass

        if chunks:
            data = b"".join(chunks)
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        raise Exception("No data received")

    def send_command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Isaac")

        command = {"type": command_type, "params": params or {}}
        try:
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            self.sock.settimeout(300.0)
            response_data = self.receive_full_response(self.sock)
            response = json.loads(response_data.decode("utf-8"))

            if response.get("status") == "error":
                raise Exception(response.get("message", "Unknown error from Isaac"))
            return response.get("result", {})
        except socket.timeout:
            self.sock = None
            raise Exception("Timeout waiting for Isaac response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            self.sock = None
            raise Exception(f"Connection to Isaac lost: {e}")
        except json.JSONDecodeError as e:
            self.sock = None
            raise Exception(f"Invalid response from Isaac: {e}")
        except Exception as e:
            self.sock = None
            raise Exception(f"Communication error with Isaac: {e}")


_isaac_connection: Optional[IsaacConnection] = None


def get_isaac_connection() -> IsaacConnection:
    """Get or create a persistent Isaac connection singleton."""
    global _isaac_connection
    if _isaac_connection is not None:
        return _isaac_connection
    _isaac_connection = IsaacConnection(host="localhost")
    if not _isaac_connection.connect():
        _isaac_connection = None
        raise Exception("Could not connect to Isaac. Make sure the Isaac addon is running.")
    return _isaac_connection


def reset_isaac_connection() -> None:
    """Disconnect and clear the global connection (used during shutdown)."""
    global _isaac_connection
    if _isaac_connection:
        _isaac_connection.disconnect()
        _isaac_connection = None
