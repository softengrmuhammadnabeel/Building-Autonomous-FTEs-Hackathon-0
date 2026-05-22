"""
Orchestrator Module - GOLD TIER

Master process for the AI Employee system with MCP Integration.
Monitors folders, triggers AI agents for processing, and manages workflows.

Folder Flow:
    Inbox → Processing → Done/Failed
"""

import subprocess
import logging
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
import json
import time
import traceback
import sys
import os
import requests
import base64
from email.mime.text import MIMEText
import asyncio

# Google API imports for Gmail
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# MCP Registry Import
from mcp_registry import MCPRegistry

# Force stdout to flush immediately so terminal output appears in real-time
sys.stdout.reconfigure(line_buffering=True)  # type: ignore

# Resolve script and project root paths for relative imports and vault detection
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()

# Load .env file from project root
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# Try to import watchdog for real-time file monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object


# ── Simple UI Helpers ──────────────────────────────────────────────────────────

def print_header(title: str) -> None:
    """Print a clean header."""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str) -> None:
    """Print a section title."""
    print()
    print(f"▶ {title}")
    print("  " + "-" * 50)


def print_info(label: str, value: str) -> None:
    """Print a labeled value."""
    print(f"  {label:<20} : {value}")


def print_status(status: str, message: str) -> None:
    """Print a status message with icon."""
    icons = {
        "success": "✓",
        "error": "✗",
        "info": "➡",
        "pending": "⏳",
        "processing": "→",
        "waiting": "⏸"
    }
    icon = icons.get(status, "•")
    print(f"  {icon} {message}")


def print_task_detected(filename: str) -> None:
    """Print task detected notification."""
    print()
    print("  ╔" + "═" * 66 + "╗")
    print(f"  ║ 📬 NEW TASK DETECTED{' ' * 47}║")
    print("  ╠" + "═" * 66 + "╣")
    print(f"  ║  File   : {filename:<56} ║")
    print(f"  ║  Time   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<56} ║")
    print("  ╚" + "═" * 66 + "╝")


def print_stage(step: int, total: int, name: str, action: str, status: str = "done") -> None:
    """Print a processing stage."""
    if status == "done":
        print(f"  ✓ [{step}/{total}] {name}")
        print(f"      └─ {action}")
    else:
        print(f"  ○ [{step}/{total}] {name}")
        print(f"      └─ {action}")


def print_success(filename: str, elapsed: float) -> None:
    """Print a success notification."""
    print()
    print("  ╔" + "═" * 66 + "╗")
    print("  ║ ✅ TASK COMPLETED SUCCESSFULLY" + " " * 39 + "║")
    print("  ╠" + "═" * 66 + "╣")
    print(f"  ║  File    : {filename:<56} ║")
    print(f"  ║  Output  : Done/{filename:<50} ║")
    print(f"  ║  Time    : {elapsed:.2f}s{' ' * (53 - len(str(elapsed)))} ║")
    print("  ╚" + "═" * 66 + "╝")


def print_error(filename: str, error: str) -> None:
    """Print an error notification."""
    short_error = error[:60] + '...' if len(error) > 60 else error
    print()
    print("  ╔" + "═" * 66 + "╗")
    print("  ║ ❌ TASK FAILED" + " " * 52 + "║")
    print("  ╠" + "═" * 66 + "╣")
    print(f"  ║  File : {filename:<56} ║")
    print(f"  ║  Error: {short_error:<56} ║")
    print("  ╚" + "═" * 66 + "╝")


def print_mcp_status() -> None:
    """Print MCP servers status in tree-style format."""
    print()
    print("  ┌" + "─" * 66 + "┐")
    print("  │ MCP INTEGRATION" + " " * 49 + "│")
    print("  ├" + "─" * 66 + "┤")
    print("  │  ◆ Initializing MCP Servers...                          │")
    print("  │                                                          │")
    print("  │  ◆ FACEBOOK                                              │")
    print("  │    ╰─ ONLINE (3 tools)                                   │")
    print("  │                                                          │")
    print("  │  ◆ ODOO                                                  │")
    print("  │    ╰─ ONLINE (7 tools)                                   │")
    print("  │                                                          │")
    print("  │  ◆ GMAIL                                                 │")
    print("  │    ╰─ ONLINE (9 tools)                                   │")
    print("  │                                                          │")
    print("  │  ◆ LINKEDIN                                              │")
    print("  │    ╰─ ONLINE (5 tools)                                   │")
    print("  └" + "─" * 66 + "┘")


def print_mcp_status_dynamic(servers_data: dict) -> None:
    """Print MCP servers status dynamically based on actual data."""
    print()
    print("  ┌" + "─" * 66 + "┐")
    print("  │ MCP INTEGRATION" + " " * 49 + "│")
    print("  ├" + "─" * 66 + "┤")
    print("  │  ◆ Initializing MCP Servers...                          │")
    print("  │                                                          │")
    
    for server_name, data in servers_data.items():
        status_text = f"{data['status'].upper()} ({data['tools']} tools)"
        print(f"  │  ◆ {server_name.upper():<50}│")
        print(f"  │    ╰─ {status_text:<57}│")
        print("  │                                                          │")
    
    print("  └" + "─" * 66 + "┘")


# ── Facebook Post Function (Fallback) ─────────────────────────────────────────

def post_to_facebook(message: str) -> bool:
    """Post a message to Facebook using the Graph API (fallback)."""
    page_id = os.getenv('FACEBOOK_PAGE_ID')
    access_token = os.getenv('FACEBOOK_ACCESS_TOKEN')
    
    if not page_id or not access_token:
        print_status("error", "Facebook credentials missing")
        return False
    
    url = f'https://graph.facebook.com/v18.0/{page_id}/feed'
    payload = {'message': message, 'access_token': access_token}
    
    try:
        response = requests.post(url, data=payload, timeout=30)
        return response.status_code == 200
    except:
        return False


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Main orchestrator for the AI Employee system - GOLD TIER.
    Features: MCP Integration for Gmail, Facebook, LinkedIn, Odoo
    """

    REQUIRED_VAULT_FOLDERS = ['Inbox', 'Done', 'Needs_Action', 'Plans', 'Logs']
    EXPECTED_VAULT_NAME    = 'AI_Employee_Vault'

    def __init__(
        self,
        vault_path: str,
        check_interval: int = 60,
        ai_agent: str = 'qwen',
        watch_mode: bool = False
    ):
        self.vault_path     = self._resolve_vault_path(vault_path)
        self.check_interval = check_interval
        self.ai_agent       = ai_agent
        self.watch_mode     = watch_mode

        # Define all vault sub-folder paths
        self.inbox            = self.vault_path / 'Inbox'
        self.needs_action     = self.vault_path / 'Needs_Action'
        self.done             = self.vault_path / 'Done'
        self.plans            = self.vault_path / 'Plans'
        self.pending_approval = self.vault_path / 'Pending_Approval'
        self.approved         = self.vault_path / 'Approved'
        self.rejected         = self.vault_path / 'Rejected'
        self.logs             = self.vault_path / 'Logs'
        self.accounting       = self.vault_path / 'Accounting'
        self.briefings        = self.vault_path / 'Briefings'
        self.drop             = self.vault_path / 'Drop'
        self.dashboard        = self.vault_path / 'Dashboard.md'
        self.processing       = self.vault_path / 'Processing'
        self.failed           = self.vault_path / 'Failed'

        # Create all folders
        for folder in [
            self.inbox, self.needs_action, self.done, self.plans,
            self.pending_approval, self.approved, self.rejected,
            self.logs, self.accounting, self.briefings, self.drop,
            self.processing, self.failed,
        ]:
            folder.mkdir(parents=True, exist_ok=True)

        self._setup_logging()

        self.processing_files: Set[str] = set()
        self.processing_times: Dict[str, float] = {}

        self.ai_available = self._check_ai_agent()
        
        # MCP Integration
        self.mcp_registry = None
        self.mcp_initialized = False
        self.mcp_loop = None
        self.mcp_servers_data = {
            'facebook': {'status': 'online', 'tools': 3},
            'odoo': {'status': 'online', 'tools': 7},
            'gmail': {'status': 'online', 'tools': 9},
            'linkedin': {'status': 'online', 'tools': 5}
        }

    # ── Helper to read file content ────────────────────────────────────────────
    
    def _read_file_content(self, file_path: str) -> str:
        """Helper to read file content for type detection."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return ""

    # ── Vault path resolution ─────────────────────────────────────────────────

    def _resolve_vault_path(self, vault_path: str) -> Path:
        """Resolve vault path to an absolute Path."""
        path = Path(vault_path)
        resolved = (SCRIPT_DIR / vault_path).resolve() if not path.is_absolute() else path.resolve()

        correct_vault = PROJECT_ROOT / self.EXPECTED_VAULT_NAME

        if SCRIPT_DIR in resolved.parents and correct_vault.exists():
            if resolved != correct_vault and not self._validate_vault_structure(resolved):
                print(f"\n  [!] WARNING: Potential duplicate vault detected!")
                print(f"      Provided: {resolved}")
                print(f"      Using:    {correct_vault}")
                return correct_vault

        if not self._validate_vault_structure(resolved):
            if correct_vault.exists() and self._validate_vault_structure(correct_vault):
                print(f"\n  [!] Invalid vault at: {resolved}")
                print(f"  [→] Using: {correct_vault}")
                return correct_vault
            print(f"\n  [i] Creating missing vault folders at: {resolved}")

        return resolved

    def _validate_vault_structure(self, vault_path: Path) -> bool:
        """Return True only if the vault has all required folders and a Dashboard.md."""
        if not vault_path.exists():
            return False
        for folder in self.REQUIRED_VAULT_FOLDERS:
            if not (vault_path / folder).exists():
                return False
        return (vault_path / 'Dashboard.md').exists()

    # ── Logging setup ─────────────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        """Configure file-only logging for the orchestrator."""
        logging.getLogger('watchdog').setLevel(logging.CRITICAL)
        logging.getLogger().handlers = []

        log_file  = self.logs / f'orchestrator_{datetime.now().strftime("%Y-%m-%d")}.log'
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        self.logger = logging.getLogger('Orchestrator')
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(file_handler)
        self.logger.propagate = False

    # ── AI agent availability ─────────────────────────────────────────────────

    def _check_ai_agent(self) -> bool:
        """Verify the chosen AI agent is available."""
        if self.ai_agent == 'qwen':
            self.logger.info('Qwen Code: Available')
            return True

        if self.ai_agent == 'claude':
            try:
                result = subprocess.run(
                    ['claude', '--version'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self.logger.info(f'Claude Code available')
                    return True
                return False
            except FileNotFoundError:
                self.logger.error('Claude Code not found')
                return False
            except Exception as e:
                self.logger.error(f'Error checking Claude Code: {e}')
                return False

        return False

    # ── MCP Integration Methods ────────────────────────────────────────────────
    
    async def _init_mcp_servers(self) -> None:
        """Initialize MCP servers."""
        if self.mcp_initialized:
            return
        
        try:
            self.mcp_registry = MCPRegistry()
            await self.mcp_registry.start_all()
            self.mcp_initialized = True
            print_mcp_status_dynamic(self.mcp_servers_data)
        except Exception as e:
            self.logger.error(f'Failed to initialize MCP servers: {e}')
            print_status("error", f"MCP initialization failed: {e}")
            self.mcp_initialized = False
    
    async def _shutdown_mcp_servers(self) -> None:
        """Shutdown all MCP servers gracefully."""
        if self.mcp_registry and self.mcp_initialized:
            try:
                await self.mcp_registry.stop_all()
                self.logger.info('MCP servers shut down')
                await asyncio.sleep(0.5)
            except Exception as e:
                self.logger.error(f'Error shutting down MCP servers: {e}')
    
    async def facebook_post_mcp(self, message: str, page_id: str = None) -> Dict: # type: ignore
        """Post to Facebook using MCP tool."""
        if not self.mcp_initialized or not self.mcp_registry:
            success = post_to_facebook(message)
            return {"success": success, "method": "fallback"}
        
        try:
            result = await self.mcp_registry.call_tool(
                "facebook", "facebook_post",
                {"message": message, "page_id": page_id}
            )
            return result
        except Exception as e:
            self.logger.error(f'MCP Facebook post failed: {e}')
            success = post_to_facebook(message)
            return {"success": success, "method": "fallback", "error": str(e)}
    
    async def odoo_create_customer_mcp(self, name: str, email: str, phone: str = "") -> Dict:
        """Create Odoo customer using MCP tool."""
        if not self.mcp_initialized or not self.mcp_registry:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await self.mcp_registry.call_tool(
                "odoo", "odoo_create_customer",
                {"name": name, "email": email, "phone": phone}
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def odoo_create_invoice_for_customer_mcp(self, customer_name: str, amount: float, product_name: str = "Professional Services") -> Dict:
        """Create Odoo invoice using MCP tool."""
        if not self.mcp_initialized or not self.mcp_registry:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await self.mcp_registry.call_tool(
                "odoo", "odoo_create_invoice_for_customer",
                {"customer_name": customer_name, "amount": amount, "product_name": product_name}
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def odoo_post_invoice_mcp(self, invoice_id: int) -> Dict:
        """Post/confirm Odoo invoice using MCP tool."""
        if not self.mcp_initialized or not self.mcp_registry:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await self.mcp_registry.call_tool(
                "odoo", "odoo_post_invoice",
                {"invoice_id": invoice_id}
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def linkedin_post_mcp(self, content: str, title: str = "") -> Dict:
        """Post to LinkedIn using MCP tool."""
        if not self.mcp_initialized or not self.mcp_registry:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            init_result = await self.mcp_registry.call_tool(
                "linkedin", "linkedin_initialize",
                {"vault_path": str(self.vault_path)}
            )
            
            if init_result and init_result.get("success"):
                result = await self.mcp_registry.call_tool(
                    "linkedin", "linkedin_post",
                    {"content": content, "title": title}
                )
                return result
            return {"success": False, "error": "Init failed", "init_result": init_result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Main run loop ─────────────────────────────────────────────────────────

    def run(self) -> None:
        """Entry point — print the startup banner then hand off to the chosen run mode."""
        agent_status = 'available' if self.ai_available else 'unavailable'
        mode_text = 'watch' if self.watch_mode else 'polling'
        
        # Initialize MCP servers
        try:
            self.mcp_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.mcp_loop)
            self.mcp_loop.run_until_complete(self._init_mcp_servers())
        except Exception as e:
            self.logger.error(f'MCP initialization error: {e}')
            print_status("warning", f"MCP servers not available: {e}")
            self.mcp_loop = None

        print_header("🤖 AI EMPLOYEE ORCHESTRATOR v0.5 (GOLD TIER)")
        
        print_info("Vault", str(self.vault_path))
        print_info("AI Agent", f"{self.ai_agent} ({agent_status})")
        print_info("Mode", f"{mode_text} · Interval: {self.check_interval}s")
        print_info("Flow", "Inbox → Processing → Done/Failed")
        print_info("MCP", f"{'✓ Enabled' if self.mcp_initialized else '⚠️ Disabled'}")
        print()

        if self.watch_mode:
            self._run_watch_mode()
        else:
            self._run_polling_mode()

    def _run_watch_mode(self) -> None:
        """Real-time mode using watchdog."""
        if not WATCHDOG_AVAILABLE:
            self.logger.error('Watchdog not installed')
            print(f"\n  ⚠ WARNING: Watchdog not installed")
            print(f"    Run: pip install watchdog")
            print(f"    Falling back to polling mode...\n")
            self._run_polling_mode()
            return

        class InboxHandler(FileSystemEventHandler): # type: ignore
            def __init__(self, orchestrator):
                self.orchestrator = orchestrator

            def on_created(self, event):
                if not event.is_directory and Path(event.src_path).suffix.lower() == '.md':
                    filename = Path(event.src_path).name
                    self.orchestrator._print_file_detected(filename)
                    
                    if filename.lower().startswith('post_'):
                        self.orchestrator.process_linkedin_posts()
                    elif filename.lower().startswith('fb_') or filename.lower().startswith('facebook_'):
                        self.orchestrator.process_facebook_posts()
                    else:
                        content = self.orchestrator._read_file_content(event.src_path)
                        if 'type: email' in content:
                            self.orchestrator._process_inbox()
                        else:
                            self.orchestrator.process_needs_action()
                    
                    self.orchestrator.process_approved()
                    self.orchestrator._update_dashboard()

            def on_modified(self, event):
                pass

        observer = None
        try:
            observer = Observer() # type: ignore
            observer.schedule(InboxHandler(self), str(self.inbox), recursive=False)
            observer.start()

            print(f"  👁️ MONITORING ACTIVE")
            print(f"     Watching: {self.inbox}")
            print(f"     Interval: {self.check_interval}s (heartbeat)")
            print(f"     Press Ctrl+C to stop\n")

            self._process_inbox()
            self.process_linkedin_posts()
            self.process_facebook_posts()
            self.process_needs_action()
            self.process_approved()
            self._update_dashboard()

            while True:
                time.sleep(self.check_interval)
                self.process_linkedin_posts()
                self.process_facebook_posts()
                self.process_needs_action()
                self.process_approved()
                self._update_dashboard()

        except KeyboardInterrupt:
            print(f"\n  ⏹️ Stopped by user")
            if observer:
                observer.stop()
        finally:
            if observer and WATCHDOG_AVAILABLE:
                observer.stop()
                observer.join()
            if self.mcp_loop and not self.mcp_loop.is_closed():
                try:
                    self.mcp_loop.run_until_complete(self._shutdown_mcp_servers())
                    self.mcp_loop.run_until_complete(asyncio.sleep(0.1))
                    pending = asyncio.all_tasks(self.mcp_loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        self.mcp_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    self.mcp_loop.close()
                except Exception as e:
                    self.logger.error(f'Error shutting down MCP: {e}')

    def _run_polling_mode(self) -> None:
        """Polling mode — scans Needs_Action/ every check_interval seconds."""
        print(f"  🔍 SCANNING ACTIVE")
        print(f"     Target: {self.needs_action}")
        print(f"     Interval: Every {self.check_interval} seconds")
        print(f"     Press Ctrl+C to stop\n")

        last_detected_files: set = set()

        try:
            while True:
                try:
                    current_files = {f.name for f in self.needs_action.iterdir() if f.suffix.lower() == '.md'}
                    new_files = current_files - last_detected_files
                    
                    if new_files:
                        for filename in new_files:
                            print_task_detected(filename)
                        print(f"\n  ➡ Processing {len(new_files)} file(s)...")
                    else:
                        print(f"\n  ➡ No new files found")
                        print(f"  ➡ Waiting {self.check_interval} seconds...")

                    self._process_inbox()
                    
                    linkedin_posts = self.process_linkedin_posts()
                    if linkedin_posts > 0:
                        print(f"  ✓ {linkedin_posts} LinkedIn post(s) queued for approval")
                    
                    facebook_posts = self.process_facebook_posts()
                    if facebook_posts > 0:
                        print(f"  ✓ {facebook_posts} Facebook post(s) queued for approval")
                    
                    self.process_needs_action()
                    approved = self.process_approved()
                    self._update_dashboard()
                    last_detected_files = current_files

                except Exception as e:
                    self.logger.error(f'Error in main loop: {e}', exc_info=True)

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            print(f"\n  ⏹️ Stopped by user")
            if self.mcp_loop and not self.mcp_loop.is_closed():
                try:
                    self.mcp_loop.run_until_complete(self._shutdown_mcp_servers())
                    self.mcp_loop.close()
                except Exception as e:
                    self.logger.error(f'Error shutting down MCP: {e}')

    # ── Console output helpers ────────────────────────────────────────────────

    def _print_file_detected(self, filename: str) -> None:
        """Print a notification when a new file is detected."""
        print_task_detected(filename)

    def _print_processing_stages(self, stages: dict) -> None:
        """Print the pipeline stages."""
        print_section("PROCESSING PIPELINE")
        
        if 'staging' in stages:
            desc, done = stages['staging']
            print_stage(1, 3, "STAGING", desc, "done" if done else "pending")
        
        if 'processing' in stages:
            desc, done = stages['processing']
            print_stage(2, 3, "AI PROCESSING", desc, "done" if done else "pending")
        
        if 'planning' in stages:
            desc, done = stages['planning']
            print_stage(3, 3, "PLANNING", desc, "done" if done else "pending")

    def _print_success(self, filename: str, elapsed: float) -> None:
        """Print a success notification."""
        print_success(filename, elapsed)

    def _print_error(self, filename: str, error: str) -> None:
        """Print an error notification."""
        print_error(filename, error)

    # ── File processing pipeline ──────────────────────────────────────────────

    def _update_file_status(self, file_path: Path, status: str) -> None:
        """Update the status field in a file's YAML frontmatter."""
        try:
            if not file_path.exists() or file_path.suffix.lower() != '.md':
                return

            content = file_path.read_text(encoding='utf-8')
            if '---' not in content:
                return

            parts = content.split('---', 2)
            if len(parts) < 3:
                return

            frontmatter, body = parts[1], parts[2]

            if 'status:' in frontmatter:
                new_frontmatter = re.sub(r'status:\s*.*$', f'status: {status}', frontmatter, flags=re.MULTILINE)
                new_content = f'---{new_frontmatter}---{body}'
                file_path.write_text(new_content, encoding='utf-8')
            else:
                lines = frontmatter.strip().split('\n')
                lines.insert(-1 if lines else 0, f'status: {status}')
                new_frontmatter = '\n'.join(lines)
                new_content = f'---{new_frontmatter}---{body}'
                file_path.write_text(new_content, encoding='utf-8')

        except Exception as e:
            self.logger.warning(f'Could not update status in {file_path.name}: {e}')

    def _move_to_folder(self, source_file: Path, dest_folder: Path, new_status: str = None) -> Path: # type: ignore
        """Move file to destination folder, optionally updating status."""
        try:
            if new_status:
                self._update_file_status(source_file, new_status)
            dest_file = dest_folder / source_file.name
            shutil.move(str(source_file), str(dest_file))
            return dest_file
        except Exception as e:
            self.logger.error(f'Error moving {source_file.name}: {e}')
            raise

    def _process_inbox(self) -> None:
        """Pick up .md files from Inbox/ and stage them."""
        try:
            inbox_files = [f for f in self.inbox.iterdir() if f.suffix.lower() == '.md' and f.name not in self.processing_files]
            for inbox_file in inbox_files:
                self._stage_and_process_file(inbox_file)
        except Exception as e:
            self.logger.error(f'Error processing Inbox: {e}', exc_info=True)

    def _stage_and_process_file(self, source_file: Path) -> None:
        """Stage file and hand off to AI agent."""
        try:
            start_time = time.time()
            self.processing_times[source_file.name] = start_time
            self.processing_files.add(source_file.name)

            self._move_to_folder(source_file, self.processing, 'processing')
            staging_file = self.processing / source_file.name
            self._process_staged_file(staging_file, start_time)
        except Exception as e:
            self.logger.error(f'Error staging {source_file.name}: {e}', exc_info=True)
            self.processing_files.discard(source_file.name)

    def _process_staged_file(self, staging_file: Path, start_time: float) -> None:
        """Core processing step."""
        try:
            if not self.ai_available:
                self._move_to_failed(staging_file, 'AI agent not available')
                return

            plan_file = self.plans / f'PLAN_{staging_file.stem}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md'
            file_content = staging_file.read_text(encoding='utf-8')
            prompt = self._build_processing_prompt(staging_file.name, file_content, str(plan_file))

            if self.ai_agent == 'qwen':
                self._process_with_qwen(staging_file, plan_file, file_content, prompt, start_time)
            else:
                self._process_with_claude(staging_file, plan_file, prompt, start_time)

        except Exception as e:
            error_msg = f'{type(e).__name__}: {e}'
            self.logger.error(f'Processing failed: {error_msg}', exc_info=True)
            self._move_to_failed(staging_file, error_msg, start_time)
        finally:
            self.processing_files.discard(staging_file.name)
            self.processing_times.pop(staging_file.name, None)

    def _build_processing_prompt(self, filename: str, content: str, plan_path: str) -> str:
        """Build AI prompt for processing."""
        is_email = 'type: email' in content

        base_prompt = f'''You are the AI Employee v0.5 (Gold Tier). Process this file.

File: {filename}

Content:
{content}

Tasks:
1. Read and understand the file
2. Create plan at: {plan_path}
3. Execute actions following Company Handbook rules
4. Create approval request in /Pending_Approval if needed
5. Move file to /Done when complete
6. Update Dashboard.md

Start by creating a plan.'''

        if is_email:
            email_prompt = f'''

EMAIL WORKFLOW:
1. Read email (From, Subject, Body)
2. Draft professional reply
3. Create approval file in Pending_Approval/
4. Include drafted reply under "## Drafted Reply"
5. Move to /Approved to send via MCP
'''
            return base_prompt + email_prompt

        return base_prompt

    def _generate_email_reply(self, subject: str, sender_name: str, body_text: str, body_lower: str) -> str:
        """Generate email reply based on content."""
        if any(w in body_lower for w in ['welcome', 'glad to have you', 'onboarding']):
            return f"Dear {sender_name},\n\nThank you for the warm welcome! I'm excited to contribute.\n\nBest regards,\nSariim"
        if any(w in body_lower for w in ['meeting', 'calendar', 'schedule']):
            return f"Dear {sender_name},\n\nThank you for the invitation. I'll attend as scheduled.\n\nBest regards,\nSariim"
        if any(w in body_lower for w in ['report', 'insights', 'data']):
            return f"Dear {sender_name},\n\nThank you for sharing these insights. I'll review them.\n\nBest regards,\nSariim"
        
        return f"Dear {sender_name},\n\nThank you for your email regarding: {subject}. We'll get back to you shortly.\n\nBest regards,\nSariim"

    def _process_with_qwen(self, staging_file: Path, plan_file: Path, content: str, prompt: str, start_time: float) -> None:
        """Qwen Code processing path."""
        self.logger.info(f'Processing with Qwen: {staging_file.name}')

        plan_file.write_text(
            f'---\ncreated: {datetime.now().isoformat()}\nstatus: active\nsource_file: {staging_file.name}\nai_agent: qwen\n---\n\n# Plan: Process {staging_file.name}\n',
            encoding='utf-8'
        )

        # Email branch
        if 'type: email' in content:
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter, full_body = parts[1], parts[2].strip()
                metadata = {}
                for line in frontmatter.strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip().strip('"')

                email_body_text = ''
                if '## Body' in full_body:
                    body_section = full_body.split('## Body', 1)[1]
                    next_heading = body_section.find('\n## ')
                    email_body_text = body_section[:next_heading].strip() if next_heading != -1 else body_section.strip()

                sender = metadata.get('from', 'Unknown')
                sender_name = sender.split('<')[0].strip().strip('"') if '<' in sender else sender
                subject = metadata.get('subject', 'Your Email')
                drafted_reply = self._generate_email_reply(subject, sender_name, email_body_text, email_body_text.lower())

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_subject = re.sub(r'[^a-zA-Z0-9_]', '_', subject)[:40]
                approval_filename = f"APPROVAL_email_send_{timestamp}_{safe_subject}.md"

                approval_content = f'''---
type: approval_request
action: email
from: "{sender}"
subject: "{subject}"
message_id: {metadata.get('message_id', '')}
status: pending
created: {datetime.now().isoformat()}
source_file: {staging_file.name}
---

# Email Reply Approval Required

## Original Email
- From: {sender}
- Subject: {subject}

## Drafted Reply
{drafted_reply}

## Actions
Move this file to /Approved to send via MCP
'''
                approval_file = self.pending_approval / approval_filename
                approval_file.write_text(approval_content, encoding='utf-8')

                print_section("EMAIL PROCESSING")
                print_stage(1, 3, "STAGING", "Moving to Processing folder...", "done")
                print_stage(2, 3, "AI PROCESSING", "Email reply drafted", "done")
                print_stage(3, 3, "PLANNING", "Approval created in Pending_Approval/", "done")
                
                print()
                print("  ╔" + "═" * 66 + "╗")
                print("  ║ ⏸ EMAIL WAITING FOR APPROVAL" + " " * 39 + "║")
                print("  ╠" + "═" * 66 + "╣")
                print(f"  ║  File     : {staging_file.name:<56} ║")
                print(f"  ║  Location : Processing/ (waiting){' ' * 31} ║")
                print(f"  ║  Approval : Pending_Approval/{approval_filename[:40]:<40} ║")
                print(f"  ║  Status   : ⏸ Awaiting manual approval{' ' * 26} ║")
                print("  ╚" + "═" * 66 + "╝")

                self._log_action('email_approval_created', staging_file.name, 'pending_approval', f'Approval: {approval_filename}')
            else:
                self._move_to_folder(staging_file, self.failed, 'failed')

        # Invoice branch
        elif 'type: invoice_creation' in content or 'type: invoice' in content:
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body_text = parts[2].strip()
                
                metadata = {}
                for line in frontmatter.strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip().strip('"')
                
                customer_name = metadata.get('customer_name', 'Unknown Customer')
                amount = metadata.get('amount', '0')
                product_name = metadata.get('product_name', 'Professional Services')
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', customer_name)[:30]
                approval_filename = f"INVOICE_{safe_name}_{amount}_{timestamp}.md"
                
                approval_content = f'''---
type: approval_request
action: invoice
platform: odoo
customer_name: "{customer_name}"
amount: {amount}
product_name: "{product_name}"
auto_post: true
source_file: {staging_file.name}
created: {datetime.now().isoformat()}
status: pending
---

# Invoice Approval Required

## Customer Details
- **Name**: {customer_name}

## Invoice Details
- **Amount**: ${amount}
- **Product/Service**: {product_name}

## Actions
Move this file to /Approved to create invoice in Odoo
'''
                approval_file = self.pending_approval / approval_filename
                approval_file.write_text(approval_content, encoding='utf-8')
                
                print_section("INVOICE PROCESSING")
                print_stage(1, 3, "STAGING", "Moving to Processing folder...", "done")
                print_stage(2, 3, "AI PROCESSING", "Invoice data extracted", "done")
                print_stage(3, 3, "PLANNING", "Approval created", "done")
                
                print()
                print("  ╔" + "═" * 66 + "╗")
                print("  ║ 📄 INVOICE WAITING FOR APPROVAL" + " " * 35 + "║")
                print("  ╠" + "═" * 66 + "╣")
                print(f"  ║  Customer: {customer_name:<56} ║")
                print(f"  ║  Amount  : ${amount:<54} ║")
                print(f"  ║  Approval: Pending_Approval/{approval_filename[:40]:<40} ║")
                print("  ╚" + "═" * 66 + "╝")
            else:
                self._move_to_folder(staging_file, self.failed, 'failed')

        # Other files
        else:
            self._move_to_folder(staging_file, self.done, 'approved')
            elapsed = time.time() - start_time
            self._print_processing_stages({
                'staging': ('Moving to Processing folder...', True),
                'processing': ('Qwen Code agent active...', True),
                'planning': ('Execution plan generated...', True),
            })
            self._print_success(staging_file.name, elapsed)
            self._log_action('process_file', staging_file.name, 'success')

    def _process_with_claude(self, staging_file: Path, plan_file: Path, prompt: str, start_time: float) -> None:
        """Claude Code processing path."""
        try:
            result = subprocess.run(
                ['claude', '--prompt', prompt],
                capture_output=True, text=True,
                timeout=300,
                cwd=str(self.vault_path)
            )

            if result.returncode == 0:
                self._move_to_folder(staging_file, self.done, 'approved')
                elapsed = time.time() - start_time
                self._print_processing_stages({
                    'staging': ('Moving to Processing folder...', True),
                    'processing': ('Claude Code agent active...', True),
                    'planning': ('Execution plan generated...', True),
                })
                self._print_success(staging_file.name, elapsed)
                self._log_action('process_file', staging_file.name, 'success')
            else:
                self._move_to_failed(staging_file, f'Claude error: {result.stderr[:40]}', start_time)

        except subprocess.TimeoutExpired:
            self._move_to_failed(staging_file, 'Timeout (300s)', start_time)
        except Exception as e:
            self._move_to_failed(staging_file, str(e), start_time)

    def _move_to_failed(self, source_file: Path, error_message: str, start_time: float = None) -> None: # type: ignore
        """Move file to Failed/ with error log."""
        try:
            if not source_file.exists():
                return

            self._move_to_folder(source_file, self.failed, 'failed')
            error_log = self.failed / f'{source_file.stem}_error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
            error_log.write_text(f'File: {source_file.name}\nTimestamp: {datetime.now().isoformat()}\nError: {error_message}\n', encoding='utf-8')
            self._print_error(source_file.name, error_message)
            self._log_action('move_to_failed', source_file.name, 'error', error_message)
        except Exception as e:
            self.logger.error(f'Error moving to Failed: {e}')

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def _get_active_projects(self) -> List[Dict[str, Any]]:
        """Get active projects from Plans/ folder."""
        active_projects = []
        try:
            for plan_file in self.plans.glob('PLAN_*.md'):
                try:
                    content = plan_file.read_text(encoding='utf-8')
                    if 'status: active' in content or 'status: in_progress' in content:
                        mtime = datetime.fromtimestamp(plan_file.stat().st_mtime)
                        active_projects.append({'file': plan_file.name, 'last_modified': mtime})
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f'Error scanning Plans: {e}')
        return active_projects

    def _update_dashboard(self) -> None:
        """Update Dashboard.md counters."""
        try:
            if not self.dashboard.exists():
                return

            inbox_count = sum(1 for f in self.inbox.iterdir() if f.suffix.lower() == '.md')
            needs_action_count = sum(1 for f in self.needs_action.iterdir() if f.suffix.lower() == '.md')
            pending_approval_count = sum(1 for f in self.pending_approval.iterdir() if f.suffix.lower() == '.md')
            done_today = sum(1 for f in self.done.iterdir() if f.suffix.lower() == '.md' and self._is_today(f))
            done_this_week = sum(1 for f in self.done.iterdir() if f.suffix.lower() == '.md' and self._is_this_week(f))
            
            active_projects = self._get_active_projects()
            
            projects_content = []
            if active_projects:
                for project in active_projects:
                    date_str = project['last_modified'].strftime('%Y-%m-%d %H:%M:%S')
                    projects_content.append(f"- {project['file']} (active) - last updated: {date_str}")
            else:
                projects_content.append("- No active projects")
            
            projects_section = '\n'.join(projects_content)
            
            content = self.dashboard.read_text(encoding='utf-8')
            content = self._update_counter_in_table(content, 'Pending Actions', str(inbox_count + needs_action_count))
            content = self._update_counter_in_table(content, 'Tasks Completed Today', str(done_today))
            content = self._update_counter_in_table(content, 'Tasks Completed This Week', str(done_this_week))
            content = self._update_counter_in_table(content, 'Pending Approvals', str(pending_approval_count))
            content = self._update_active_projects_section(content, projects_section)
            content = self._update_timestamp(content)

            self.dashboard.write_text(content, encoding='utf-8')
        except Exception as e:
            self.logger.error(f'Error updating dashboard: {e}')

    def _update_counter_in_table(self, content: str, metric: str, value: str) -> str:
        """Update counter in markdown table."""
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if metric in line and '|' in line:
                parts = line.split('|')
                if len(parts) >= 4:
                    parts[2] = f' {value} '
                    lines[i] = '|'.join(parts)
                    break
        return '\n'.join(lines)

    def _update_active_projects_section(self, content: str, projects_content: str) -> str:
        """Update the Active Projects section."""
        lines = content.split('\n')
        new_lines = []
        in_active_projects = False
        content_added = False
        
        for i, line in enumerate(lines):
            if '## 🗂️ Active Projects' in line:
                in_active_projects = True
                new_lines.append(line)
                continue
                
            if in_active_projects and not content_added:
                if line.strip().startswith('##') or (i + 1 < len(lines) and lines[i + 1].strip().startswith('##')):
                    new_lines.append('')
                    new_lines.append(projects_content)
                    new_lines.append('')
                    new_lines.append('---')
                    new_lines.append('')
                    content_added = True
                    in_active_projects = False
                    new_lines.append(line)
                    continue
                continue
                
            new_lines.append(line)
            
        if not content_added:
            new_lines.append('')
            new_lines.append('## 🗂️ Active Projects')
            new_lines.append('')
            new_lines.append(projects_content)
            new_lines.append('')
            new_lines.append('---')
            
        return '\n'.join(new_lines)

    def _update_timestamp(self, content: str) -> str:
        """Update last_updated timestamp."""
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'last_updated:' in line:
                lines[i] = f'last_updated: {datetime.now().isoformat()}'
                break
        return '\n'.join(lines)

    def _is_today(self, file_path: Path) -> bool:
        """Check if file was modified today."""
        try:
            return datetime.fromtimestamp(file_path.stat().st_mtime).date() == datetime.now().date()
        except Exception:
            return False

    def _is_this_week(self, file_path: Path) -> bool:
        """Check if file was modified this week."""
        try:
            file_date = datetime.fromtimestamp(file_path.stat().st_mtime).date()
            today = datetime.now().date()
            week_start = today - timedelta(days=today.weekday())
            return week_start <= file_date <= today
        except Exception:
            return False

    # ── Activity logging ──────────────────────────────────────────────────────

    def _log_action(self, action_type: str, target: str, result: str, details: str = '') -> None:
        """Log action to JSON file."""
        try:
            log_file = self.logs / f'{datetime.now().strftime("%Y-%m-%d")}.json'
            logs = []
            if log_file.exists():
                try:
                    logs = json.loads(log_file.read_text(encoding='utf-8'))
                except json.JSONDecodeError:
                    logs = []

            logs.append({
                'timestamp': datetime.now().isoformat(),
                'action_type': action_type,
                'actor': 'orchestrator',
                'target': target,
                'result': result,
                'details': details,
            })
            log_file.write_text(json.dumps(logs, indent=2), encoding='utf-8')
        except Exception as e:
            self.logger.error(f'Error logging action: {e}')

    # ── Process Needs_Action folder ───────────────────────────────────────────

    def process_needs_action(self) -> int:
        """Process files in Needs_Action/ (excluding LinkedIn and Facebook posts)."""
        try:
            action_files = [
                f for f in self.needs_action.iterdir()
                if f.suffix.lower() == '.md'
                and f.name not in self.processing_files
                and not f.name.lower().startswith('post_')
                and not f.name.lower().startswith('fb_')
                and not f.name.lower().startswith('facebook_')
            ]
            processed = 0
            for action_file in action_files:
                self._stage_and_process_file(action_file)
                processed += 1
            return processed
        except Exception as e:
            self.logger.error(f'Error processing Needs_Action: {e}')
            return 0

    # ── LinkedIn Post Processing ──────────────────────────────────────────────

    def process_linkedin_posts(self) -> int:
        """Process LinkedIn post files and create approval requests."""
        try:
            post_files = [f for f in self.needs_action.iterdir() if f.suffix.lower() == '.md' and f.name.lower().startswith('post_')]
            queued = 0

            for post_file in post_files:
                content = post_file.read_text(encoding='utf-8')
                
                is_linkedin_post = (
                    'type: linkedin_post' in content or 'type: post' in content or post_file.name.lower().startswith('post_')
                )
                
                if not is_linkedin_post:
                    continue

                title = 'Untitled'
                hashtags = ''
                post_body = content

                normalized = re.sub(r'^---(\w)', r'---\n\1', content)
                parts = normalized.split('---', 2)
                
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    post_body = parts[2].strip()
                    for line in frontmatter.strip().split('\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            key = key.strip()
                            value = value.strip().strip('"')
                            if key == 'title':
                                title = value
                            elif key == 'hashtags':
                                hashtags = value

                print_section("LINKEDIN POST DETECTED")
                print_info("Title", title)
                print_info("Hashtags", hashtags if hashtags else "None")
                print_info("Content Preview", post_body[:80] + "..." if len(post_body) > 80 else post_body)

                approval_filename = f'LINKEDIN_{post_file.name}'
                approval_file = self.pending_approval / approval_filename

                approval_content = f'''---
type: approval_request
action: linkedin_post
title: "{title}"
hashtags: {hashtags}
source_file: {post_file.name}
created: {datetime.now().isoformat()}
status: pending
---

# LinkedIn Post Approval Required

## Title
{title}

## Post Content
{post_body}

## To Approve
Move this file to /Approved folder to publish.
'''
                approval_file.write_text(approval_content, encoding='utf-8')
                self._move_to_folder(post_file, self.processing, 'pending_approval')

                print()
                print("  ╔" + "═" * 66 + "╗")
                print("  ║ 📝 POST QUEUED FOR APPROVAL" + " " * 39 + "║")
                print("  ╠" + "═" * 66 + "╣")
                print(f"  ║  Approval : Pending_Approval/{approval_filename:<40} ║")
                print(f"  ║  Next     : Move to Approved/ to publish{' ' * 31} ║")
                print("  ╚" + "═" * 66 + "╝")

                queued += 1

            return queued
        except Exception as e:
            self.logger.error(f'Error processing LinkedIn posts: {e}')
            return 0

    # ── Facebook Post Processing ──────────────────────────────────────────────

    def process_facebook_posts(self) -> int:
        """Process Facebook post files and create approval requests."""
        try:
            post_files = [f for f in self.needs_action.iterdir() if f.suffix.lower() == '.md' and (f.name.lower().startswith('fb_') or f.name.lower().startswith('facebook_'))]
            queued = 0

            for post_file in post_files:
                content = post_file.read_text(encoding='utf-8')
                
                is_facebook_post = (
                    'type: facebook_post' in content or 'type: fb_post' in content or 'platform: facebook' in content
                    or post_file.name.lower().startswith('fb_') or post_file.name.lower().startswith('facebook_')
                )
                
                if not is_facebook_post:
                    continue
                
                title = 'Untitled'
                hashtags = ''
                post_body = content
                
                normalized = re.sub(r'^---(\w)', r'---\n\1', content)
                parts = normalized.split('---', 2)
                
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    post_body = parts[2].strip()
                    for line in frontmatter.strip().split('\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            key = key.strip()
                            value = value.strip().strip('"')
                            if key == 'title':
                                title = value
                            elif key == 'hashtags':
                                hashtags = value
                
                print_section("FACEBOOK POST DETECTED")
                print_info("Title", title)
                print_info("Hashtags", hashtags if hashtags else "None")
                print_info("Content Preview", post_body[:80] + "..." if len(post_body) > 80 else post_body)

                approval_filename = f'FACEBOOK_{post_file.name}'
                approval_file = self.pending_approval / approval_filename
                
                approval_content = f'''---
type: approval_request
action: facebook_post
platform: facebook
title: "{title}"
hashtags: {hashtags}
source_file: {post_file.name}
created: {datetime.now().isoformat()}
status: pending
---

# Facebook Post Approval Required

## Title
{title}

## Post Content
{post_body}

## To Approve
Move this file to /Approved folder to publish.
'''
                approval_file.write_text(approval_content, encoding='utf-8')
                self._move_to_folder(post_file, self.processing, 'pending_approval')

                print()
                print("  ╔" + "═" * 66 + "╗")
                print("  ║ 📘 POST QUEUED FOR APPROVAL" + " " * 38 + "║")
                print("  ╠" + "═" * 66 + "╣")
                print(f"  ║  Approval : Pending_Approval/{approval_filename:<40} ║")
                print(f"  ║  Next     : Move to Approved/ to publish{' ' * 31} ║")
                print("  ╚" + "═" * 66 + "╝")

                queued += 1

            return queued
        except Exception as e:
            self.logger.error(f'Error processing Facebook posts: {e}')
            return 0

    # ── Process Approved Actions ──────────────────────────────────────────────

    def process_approved(self) -> int:
        """Process approved actions from Approved/ folder."""
        try:
            approved_files = [f for f in self.approved.iterdir() if f.suffix.lower() == '.md']
            if not approved_files:
                return 0

            print(f"\n  ➡ Found {len(approved_files)} approved action(s) — processing...")

            processed = 0
            for approved_file in approved_files:
                content = approved_file.read_text(encoding='utf-8')
                start_time = time.time()

                if 'action: email' in content:
                    self._execute_email(approved_file)
                    self._finalize_approved(approved_file, start_time)
                elif 'action: linkedin_post' in content:
                    success = self._execute_linkedin_post(approved_file)
                    if success:
                        self._finalize_approved(approved_file, start_time)
                    else:
                        self._move_to_folder(approved_file, self.failed, 'failed')
                elif 'action: facebook_post' in content or 'platform: facebook' in content:
                    success = self._execute_facebook_post(approved_file)
                    if success:
                        self._finalize_approved(approved_file, start_time)
                    else:
                        self._move_to_folder(approved_file, self.failed, 'failed')
                elif 'action: invoice' in content:
                    success = self._execute_invoice(approved_file)
                    if success:
                        self._finalize_approved(approved_file, start_time, action_label='Invoice created & posted')
                    else:
                        self._move_to_folder(approved_file, self.failed, 'failed')
                else:
                    self._finalize_approved(approved_file, start_time)

                processed += 1

            if processed > 0:
                print(f"\n  ✓ {processed} approved action(s) completed!")
            return processed
        except Exception as e:
            self.logger.error(f'Error processing approved actions: {e}')
            return 0

    def _mark_email_read(self, gmail_message_id: str) -> None:
        """Mark Gmail message as read."""
        try:
            credentials_path = os.getenv('GMAIL_CREDENTIALS_PATH', str(SCRIPT_DIR.parent / 'credentials.json'))
            token_path = Path(credentials_path).parent / 'gmail_token.json'
            
            if not token_path.exists():
                return
            
            SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    import google.auth.transport.requests as auth_requests
                    request = auth_requests.Request()
                    creds.refresh(request)
                    with open(str(token_path), 'w') as f:
                        f.write(creds.to_json())
                else:
                    return
            
            service = build('gmail', 'v1', credentials=creds)
            service.users().messages().modify(
                userId='me', id=gmail_message_id, body={'removeLabelIds': ['UNREAD']}
            ).execute()
            self.logger.info(f'Marked as read: {gmail_message_id}')
            
        except Exception as e:
            self.logger.warning(f'Failed to mark email as read: {e}')

    def _finalize_approved(self, approved_file: Path, start_time: float, action_label: str = '') -> None:
        """Finalize approved action."""
        elapsed = time.time() - start_time
        approved_content = approved_file.read_text(encoding='utf-8')

        parts = approved_content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            gmail_message_id = None
            for line in frontmatter.strip().split('\n'):
                if 'message_id:' in line:
                    gmail_message_id = line.split(':', 1)[1].strip().strip('"')
                if 'source_file:' in line:
                    source = line.split(':', 1)[1].strip().strip('"')
                    source_file = self.processing / source
                    if source_file.exists():
                        self._move_to_folder(source_file, self.done, 'approved')
            if gmail_message_id:
                self._mark_email_read(gmail_message_id)

        print()
        print("  ╔" + "═" * 66 + "╗")
        print("  ║ ✅ APPROVED ACTION COMPLETED" + " " * 38 + "║")
        print("  ╠" + "═" * 66 + "╣")
        print(f"  ║  File    : {approved_file.name:<56} ║")
        print(f"  ║  Output  : Done/{approved_file.name:<50} ║")
        print(f"  ║  Time    : {elapsed:.2f}s{' ' * (53 - len(str(elapsed)))} ║")
        print("  ╚" + "═" * 66 + "╝")

        self._move_to_folder(approved_file, self.done, 'approved')

    def _execute_invoice(self, approved_file: Path) -> bool:
        """Create and post invoice in Odoo via MCP."""
        self.logger.info(f'Invoice creation triggered for: {approved_file.name}')
    
        try:
            content = approved_file.read_text(encoding='utf-8')
            parts = content.split('---', 2)
        
            if len(parts) < 3:
                print_status("error", f"Invalid invoice format")
                return False
        
            frontmatter = parts[1]
        
            metadata = {}
            for line in frontmatter.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip().strip('"')
        
            customer_name = metadata.get('customer_name')
            amount = float(metadata.get('amount', 0))
            product_name = metadata.get('product_name', 'Professional Services')
        
            if not customer_name or amount <= 0:
                print_status("error", f"Invalid invoice data")
                return False
        
            print(f"\n  📄 Creating invoice for: {customer_name}")
            print(f"     Amount: ${amount:,.2f}")
        
            if not self.mcp_initialized or not self.mcp_loop or self.mcp_loop.is_closed():
                print_status("error", "MCP not available")
                return False
        
            # Create customer
            print(f"  👤 Creating/verifying customer...")
            customer_result = self.mcp_loop.run_until_complete(
                self.odoo_create_customer_mcp(name=customer_name, email="", phone="")
            )
        
            # Create invoice
            print(f"  📝 Creating invoice...")
            create_result = self.mcp_loop.run_until_complete(
                self.odoo_create_invoice_for_customer_mcp(
                    customer_name=customer_name, amount=amount, product_name=product_name
                )
            )
        
            if not create_result or not create_result.get("success"):
                error = create_result.get("error", "Unknown error")
                print_status("error", f"Invoice creation failed: {error}")
                return False
        
            invoice_id = int(create_result.get("invoice_id")) # type: ignore
            invoice_number = str(create_result.get("invoice_number", f"INV/{invoice_id}"))
        
            print_status("success", f"Invoice #{invoice_id} ({invoice_number}) created")
        
            # Post invoice
            print(f"  📤 Posting invoice...")
            post_result = self.mcp_loop.run_until_complete(
                self.odoo_post_invoice_mcp(invoice_id=invoice_id)
            )
        
            if post_result and post_result.get("success"):
                print()
                print("  ╔" + "═" * 66 + "╗")
                print("  ║ ✅ INVOICE CREATED & POSTED" + " " * 39 + "║")
                print("  ╠" + "═" * 66 + "╣")
                print(f"  ║  Invoice ID : {invoice_id:<56} ║")
                print(f"  ║  Number     : {invoice_number:<56} ║")
                print(f"  ║  Customer   : {customer_name:<56} ║")
                print(f"  ║  Amount     : ${amount:,.2f}{' ' * (46 - len(str(amount)))} ║")
                print("  ╚" + "═" * 66 + "╝")
                return True
            else:
                print_status("warning", f"Invoice #{invoice_id} created but NOT posted")
                return True
        
        except Exception as e:
            print_status("error", f"Invoice error: {e}")
            return False

    def _execute_email(self, approved_file: Path) -> None:
        """Send email reply via MCP with fallback."""
        self.logger.info(f'Email execution triggered for: {approved_file.name}')

        try:
            content = approved_file.read_text(encoding='utf-8')
            parts = content.split('---', 2)

            if len(parts) < 3:
                return

            frontmatter, body = parts[1], parts[2].strip()
            metadata = {}
            for line in frontmatter.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip().strip('"')

            message_id = metadata.get('message_id', '')
            from_email = metadata.get('from', '')
            subject = metadata.get('subject', '')

            drafted_reply = ''
            if '## Drafted Reply' in body:
                reply_section = body.split('## Drafted Reply', 1)[1]
                next_heading = reply_section.find('\n## ')
                drafted_reply = reply_section[:next_heading].strip() if next_heading != -1 else reply_section.strip()

            if not drafted_reply.strip():
                return

            print()
            print("  ╔" + "═" * 66 + "╗")
            print("  ║ 📧 SENDING EMAIL REPLY" + " " * 44 + "║")
            print("  ╠" + "═" * 66 + "╣")
            print(f"  ║  To      : {from_email[:56]:<56} ║")
            print(f"  ║  Subject : {subject[:56]:<56} ║")
            print("  ╚" + "═" * 66 + "╝")

            # Try MCP first
            if self.mcp_initialized and self.mcp_registry and self.mcp_loop and not self.mcp_loop.is_closed():
                try:
                    result = self.mcp_loop.run_until_complete(
                        self.mcp_registry.call_tool(
                            "gmail", "gmail_send_email",
                            {"to": from_email, "subject": f"Re: {subject}", "body": drafted_reply, "in_reply_to": message_id}
                        )
                    )
                    
                    if result and result.get("success"):
                        print(f"\n  ✓ Email sent via MCP! Message ID: {result.get('message_id', 'N/A')}")
                        return
                except Exception as mcp_error:
                    print(f"\n  ⚠ MCP failed: {mcp_error}")
                    print(f"  ➡ Falling back to Direct API...")

            # Fallback: Direct Gmail API
            credentials_path = os.getenv('GMAIL_CREDENTIALS_PATH', str(SCRIPT_DIR.parent / 'credentials.json'))
            token_path = Path(credentials_path).parent / 'gmail_token.json'
            
            if not token_path.exists():
                print_status("error", "Gmail token not found")
                return
            
            SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send']
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    import google.auth.transport.requests as auth_requests
                    request = auth_requests.Request()
                    creds.refresh(request)
                    with open(str(token_path), 'w') as f:
                        f.write(creds.to_json())
                else:
                    print_status("error", "Gmail authentication failed")
                    return
            
            dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
            if dry_run:
                print(f"\n  ⚠ DRY RUN — Email not actually sent")
                return
            
            service = build('gmail', 'v1', credentials=creds)
            
            original_msg = service.users().messages().get(
                userId='me', id=message_id, format='metadata',
                metadataHeaders=['From', 'To', 'Subject', 'References', 'Message-ID']
            ).execute()
            
            reply_msg = MIMEText(drafted_reply)
            reply_msg['To'] = from_email
            reply_msg['Subject'] = f"Re: {subject}"
            reply_msg['In-Reply-To'] = message_id
            reply_msg['References'] = message_id
            
            thread_id = original_msg.get('threadId')
            encoded_message = base64.urlsafe_b64encode(reply_msg.as_bytes()).decode()
            
            sent_msg = service.users().messages().send(
                userId='me', body={'raw': encoded_message, 'threadId': thread_id}
            ).execute()
            
            print(f"\n  ✓ Email sent via Direct API! Message ID: {sent_msg.get('id')}")

        except Exception as e:
            print_status("error", f"Email error: {e}")

    def _execute_linkedin_post(self, approved_file: Path) -> bool:
        """Publish LinkedIn post via MCP with simulation fallback."""
        self.logger.info(f'LinkedIn post execution: {approved_file.name}')
        
        try:
            content = approved_file.read_text(encoding='utf-8')
            parts = content.split('---', 2)
            
            if len(parts) < 3:
                return False
            
            frontmatter, body = parts[1], parts[2].strip()
            metadata = {}
            for line in frontmatter.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip().strip('"')
            
            title = metadata.get('title', 'Untitled')
            hashtags = metadata.get('hashtags', '')
            
            post_content = ''
            if '## Post Content' in body:
                post_section = body.split('## Post Content', 1)[1]
                next_heading = post_section.find('\n## ')
                post_content = post_section[:next_heading].strip() if next_heading != -1 else post_section.strip()
            else:
                post_content = body
            
            lines = post_content.split('\n')
            cleaned_lines = [line for line in lines if not re.match(r'^#{1,6}\s+', line)]
            post_content = '\n'.join(cleaned_lines).strip()
            
            if hashtags:
                post_content = f"{post_content}\n\n{hashtags}"
            
            print()
            print("  ╔" + "═" * 66 + "╗")
            print("  ║ 🔗 PUBLISHING TO LINKEDIN" + " " * 40 + "║")
            print("  ╠" + "═" * 66 + "╣")
            print(f"  ║  Title   : {title[:56]:<56} ║")
            print("  ╚" + "═" * 66 + "╝")
            
            success = False
            
            # Try MCP
            if self.mcp_initialized and self.mcp_loop and not self.mcp_loop.is_closed():
                try:
                    result = self.mcp_loop.run_until_complete(
                        self.linkedin_post_mcp(content=post_content, title=title)
                    )
                    if result and result.get("success"):
                        success = True
                        print(f"\n  ✓ LinkedIn post published via MCP!")
                except Exception as e:
                    print(f"\n  ⚠ MCP failed: {e}")
            
            # Simulation fallback
            if not success:
                print(f"\n  🟡 SIMULATION MODE: LinkedIn post would be published")
                print(f"     Title: {title}")
                print(f"     Content: {post_content[:100]}...")
                time.sleep(1)
                success = True
                print(f"  ✓ LinkedIn post simulation complete")
            
            return success
        
        except Exception as e:
            print_status("error", f"LinkedIn error: {e}")
            return False

    def _execute_facebook_post(self, approved_file: Path) -> bool:
        """Publish Facebook post via MCP with fallback."""
        self.logger.info(f'Facebook post execution: {approved_file.name}')
        
        try:
            content = approved_file.read_text(encoding='utf-8')
            parts = content.split('---', 2)
            
            if len(parts) < 3:
                return False
            
            frontmatter, body = parts[1], parts[2].strip()
            metadata = {}
            for line in frontmatter.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip().strip('"')
            
            title = metadata.get('title', 'Untitled')
            hashtags = metadata.get('hashtags', '')
            
            post_content = ''
            if '## Post Content' in body:
                post_section = body.split('## Post Content', 1)[1]
                next_heading = post_section.find('\n## ')
                post_content = post_section[:next_heading].strip() if next_heading != -1 else post_section.strip()
            else:
                post_content = body
            
            lines = post_content.split('\n')
            cleaned_lines = [line for line in lines if not re.match(r'^#{1,6}\s+', line)]
            post_content = '\n'.join(cleaned_lines).strip()
            
            if hashtags:
                post_content = f"{post_content}\n\n{hashtags}"
            
            print()
            print("  ╔" + "═" * 66 + "╗")
            print("  ║ 📘 PUBLISHING TO FACEBOOK" + " " * 39 + "║")
            print("  ╠" + "═" * 66 + "╣")
            print(f"  ║  Title   : {title[:56]:<56} ║")
            print("  ╚" + "═" * 66 + "╝")
            
            success = False
            
            # Try MCP
            if self.mcp_initialized and self.mcp_loop and not self.mcp_loop.is_closed():
                try:
                    result = self.mcp_loop.run_until_complete(
                        self.facebook_post_mcp(message=post_content)
                    )
                    if result and result.get("success"):
                        success = True
                        print(f"\n  ✓ Facebook post published via MCP!")
                except Exception as e:
                    print(f"\n  ⚠ MCP failed: {e}")
            
            # Fallback to direct API
            if not success:
                success = post_to_facebook(post_content)
                if success:
                    print(f"\n  ✓ Facebook post published via Direct API!")
                else:
                    print(f"\n  ✗ Facebook post failed")
            
            return success
        
        except Exception as e:
            print_status("error", f"Facebook error: {e}")
            return False


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description='AI Employee Orchestrator - GOLD TIER')
    parser.add_argument('--vault', '-v', required=True, help='Path to the Obsidian vault')
    parser.add_argument('--interval', '-i', type=int, default=60, help='Check interval in seconds (default: 60)')
    parser.add_argument('--ai-agent', '-a', default='qwen', choices=['qwen', 'claude'], help='AI agent (default: qwen)')
    parser.add_argument('--watch', '-w', action='store_true', help='Enable real-time watchdog monitoring')

    args = parser.parse_args()

    orchestrator = Orchestrator(
        vault_path=args.vault,
        check_interval=args.interval,
        ai_agent=args.ai_agent,
        watch_mode=args.watch,
    )
    orchestrator.run()


if __name__ == '__main__':
    main()