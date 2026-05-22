"""
MCP Central Registry - Manages all MCP servers as subprocesses
Handles the full MCP initialize → initialized → tools/list handshake
required by the official MCP Python SDK.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from dotenv import load_dotenv

# ✅ Set to WARNING only - but keeps essential MCP handshake logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('MCPRegistry')


class MCPRegistry:
    """Central registry managing all MCP servers"""

    def __init__(self):
        self.base_dir = Path(__file__).parent

        self.servers = {
            "facebook": {
                "script": str(self.base_dir / "facebook_mcp_server.py"),
                "process": None,
                "status": "stopped",
                "tools": [],
                "started_at": None,
                "_stderr_task": None,
                "_initialized": False,
            },
            "odoo": {
                "script": str(self.base_dir / "odoo_mcp_server.py"),
                "process": None,
                "status": "stopped",
                "tools": [],
                "started_at": None,
                "_stderr_task": None,
                "_initialized": False,
            },
            "gmail": {
                "script": str(self.base_dir / "gmail_watcher.py"),
                "process": None,
                "status": "stopped",
                "tools": [],
                "started_at": None,
                "_stderr_task": None,
                "_initialized": False,
            },
            "linkedin": {
                "script": str(self.base_dir / "linkedin_poster.py"),
                "process": None,
                "status": "stopped",
                "tools": [],
                "started_at": None,
                "_stderr_task": None,
                "_initialized": False,
                "requires_playwright": True,
                "env_vars": ["LINKEDIN_EMAIL", "LINKEDIN_PASSWORD"],
            },
        }
        self.request_counter = 1

    # ── stderr drainer - SILENT but keeps pipe alive ───────────────────────────────

    async def _drain_stderr(self, server_name: str) -> None:
        """Read stderr - SILENT but keeps pipe from blocking"""
        config = self.servers[server_name]
        process = config.get("process")
        if not process or not process.stderr:
            return
        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                # ✅ IMPORTANT: Read but DON'T print - keeps pipe alive
                # This ensures LinkedIn server doesn't block on stderr
                pass
        except Exception:
            pass

    # ── Low-level send / receive ───────────────────────────────────────────────

    async def _send(self, server_name: str, payload: dict) -> None:
        """Send one JSON-RPC message to the server stdin."""
        process = self.servers[server_name]["process"]
        line = json.dumps(payload) + "\n"
        process.stdin.write(line.encode())
        await process.stdin.drain()

    async def _recv(self, server_name: str, timeout: float = 10.0) -> Optional[dict]:
        """Read one JSON-RPC response from the server stdout."""
        process = self.servers[server_name]["process"]
        try:
            raw = await asyncio.wait_for(process.stdout.readline(), timeout=timeout)
            if not raw:
                return None
            return json.loads(raw.decode())
        except asyncio.TimeoutError:
            logger.error(f"[{server_name}] Timeout waiting for response")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"[{server_name}] JSON decode error: {e}")
            return None

    # ── MCP initialize handshake - QUIET ───────────────────────────────────────

    async def _do_initialize_handshake(self, server_name: str) -> bool:
        """Perform MCP handshake - QUIET MODE"""
        config = self.servers[server_name]

        req_id = self.request_counter
        self.request_counter += 1

        await self._send(server_name, {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": False},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "mcp-registry",
                    "version": "1.0.0"
                }
            }
        })

        response = await self._recv(server_name, timeout=15.0)
        if response is None or "error" in response:
            return False

        await self._send(server_name, {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        config["_initialized"] = True
        return True

    # ── Start / stop ───────────────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start all MCP servers - SILENT"""
        for server_name in self.servers:
            await self.start_server(server_name)

    async def start_server(self, server_name: str) -> bool:
        """Start an individual MCP server - QUIET but FUNCTIONAL"""
        config = self.servers[server_name]
        script_path = Path(config["script"])

        if not script_path.exists():
            config["status"] = "missing"
            return False

        if server_name == "linkedin":
            env_path = Path(__file__).parent.parent / '.env'
            load_dotenv(env_path)

        try:
            if server_name == "linkedin" and sys.platform == "linux":
                env = {**os.environ, "DISPLAY": ":99"}
            else:
                env = os.environ.copy()

            process = await asyncio.create_subprocess_exec(
                sys.executable, str(script_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            config["process"] = process
            config["status"] = "running"
            config["started_at"] = datetime.now().isoformat()
            config["_initialized"] = False

            # Start silent stderr drainer (reads but doesn't print)
            task = asyncio.create_task(self._drain_stderr(server_name))
            config["_stderr_task"] = task

            # Give server time to boot
            wait_time = 3 if server_name == "linkedin" else 2
            await asyncio.sleep(wait_time)

            # MCP handshake (quiet)
            ok = await self._do_initialize_handshake(server_name)
            if not ok:
                config["status"] = "failed"
                return False

            # Get tools (quiet)
            tools = await self.list_tools(server_name)
            config["tools"] = tools

            return True

        except Exception as e:
            logger.error(f"Failed to start {server_name}: {e}")
            config["status"] = "failed"
            return False

    async def stop_server(self, server_name: str) -> None:
        """Stop a specific server and clean up."""
        config = self.servers.get(server_name)
        if not config or not config["process"]:
            return

        task = config.get("_stderr_task")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        config["_stderr_task"] = None

        try:
            process = config["process"]
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

            if process.stdin:
                process.stdin.close()
        except Exception:
            pass
        finally:
            config["process"] = None
            config["status"] = "stopped"
            config["_initialized"] = False

    async def stop_all(self) -> None:
        """Stop all servers."""
        for server_name in list(self.servers.keys()):
            await self.stop_server(server_name)

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── List tools - QUIET ─────────────────────────────────────────────────────

    async def list_tools(self, server_name: str) -> List[Dict]:
        """List available tools - QUIET"""
        config = self.servers.get(server_name)
        if not config or config["status"] != "running" or not config.get("_initialized"):
            return []

        req_id = self.request_counter
        self.request_counter += 1

        await self._send(server_name, {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/list"
        })

        response = await self._recv(server_name, timeout=10.0)
        if response is None or "error" in response:
            return []

        result = response.get("result", {})
        if isinstance(result, dict):
            tools = result.get("tools", [])
        elif isinstance(result, list):
            tools = result
        else:
            tools = []

        return tools

    # ── Call tool ──────────────────────────────────────────────────────────────

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict = None, # type: ignore
    ) -> Dict:
        """Call an MCP tool on a specific server."""
        if arguments is None:
            arguments = {}

        config = self.servers.get(server_name)
        if not config:
            return {"error": f"Server '{server_name}' not found"}

        if config["status"] != "running":
            ok = await self.start_server(server_name)
            if not ok:
                return {"error": f"Server '{server_name}' could not be started"}

        if not config.get("_initialized"):
            return {"error": f"Server '{server_name}' MCP handshake not complete"}

        req_id = self.request_counter
        self.request_counter += 1

        await self._send(server_name, {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            }
        })

        timeout = 120.0 if (server_name == "linkedin" and tool_name == "linkedin_post") else 30.0
        response = await self._recv(server_name, timeout=timeout)

        if response is None:
            config["status"] = "timeout"
            return {"success": False, "error": f"Request timeout after {timeout}s"}

        if "error" in response:
            return {"success": False, "error": response["error"]}

        result_content = response.get("result", {})

        if isinstance(result_content, dict):
            content_list = result_content.get("content", [])
            if content_list and isinstance(content_list, list):
                text = content_list[0].get("text", "{}")
                try:
                    return json.loads(text)
                except Exception:
                    return {"success": True, "result": text}

        if isinstance(result_content, list) and result_content:
            text = result_content[0].get("text", "{}")
            try:
                return json.loads(text)
            except Exception:
                return {"success": True, "result": text}

        return {"success": True, "result": result_content}

    # ── Health check ───────────────────────────────────────────────────────────

    async def health_check(self, server_name: str) -> Dict:
        """Health check for a server."""
        config = self.servers.get(server_name)
        if not config:
            return {"status": "unknown", "error": "Server not found"}

        process = config.get("process")
        if not process or process.returncode is not None:
            return {"status": "dead", "pid": None}

        result = {
            "status": "healthy" if config["status"] == "running" else config["status"],
            "pid": process.pid,
            "started_at": config.get("started_at"),
            "initialized": config.get("_initialized", False),
            "tools_count": len(config.get("tools", [])),
        }

        if server_name == "linkedin":
            result["linkedin_credentials_loaded"] = bool(os.getenv("LINKEDIN_EMAIL"))
            result["dry_run"] = os.getenv("DRY_RUN", "false").lower() == "true"

        return result

    # ── Get server status ──────────────────────────────────────────────────────

    def get_server_status(self, server_name: Optional[str] = None) -> Dict:
        """Get status of all or specific server (sync method)"""
        if server_name:
            config = self.servers.get(server_name, {})
            process = config.get("process")
            pid = process.pid if process is not None else None

            return {
                "name": server_name,
                "status": config.get("status", "unknown"),
                "initialized": config.get("_initialized", False),
                "tools": [t.get('name') for t in config.get("tools", [])],
                "pid": pid,
            }
        else:
            return {
                name: {
                    "status": config.get("status", "unknown"),
                    "initialized": config.get("_initialized", False),
                    "tools_count": len(config.get("tools", [])),
                }
                for name, config in self.servers.items()
            }


# ── Main entry point for testing ──────────────────────────────────────────────

async def main():
    """Test MCP Registry with all servers including LinkedIn"""
    registry = MCPRegistry()

    try:
        print("\n" + "=" * 60)
        print("🚀 Testing MCP Servers via Registry")
        print("=" * 60 + "\n")

        await registry.start_all()

        for server_name in registry.servers:
            health = await registry.health_check(server_name)
            tools = await registry.list_tools(server_name)
            print(f"✅ {server_name.upper()}: {health['status']} ({len(tools)} tools)")

    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user")

    finally:
        print("\n" + "=" * 60)
        print("🧹 Cleaning up...")
        await registry.stop_all()
        print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())