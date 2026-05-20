"""
Orchestrator Module

Master process for the AI Employee system.
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

# Force stdout to flush immediately so terminal output appears in real-time
sys.stdout.reconfigure(line_buffering=True)  # type: ignore

# Resolve script and project root paths for relative imports and vault detection
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()

# Load .env file from project root (contains API keys, credentials paths, etc.)
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

# Try to import watchdog for real-time file monitoring (optional dependency)
# Falls back to polling mode if not installed
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


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Main orchestrator for the AI Employee system.

    Responsibilities:
    - Monitor Inbox for new Markdown files dropped by watchers
    - Stage files in Processing/ during work to avoid double-processing
    - Trigger the configured AI agent (Qwen Code / Claude Code) to handle the file
    - Move completed files → Done/, failed files → Failed/
    - Update Dashboard.md counters and write JSON activity logs
    """

    # Folders that must exist for a valid vault
    REQUIRED_VAULT_FOLDERS = ['Inbox', 'Done', 'Needs_Action', 'Plans', 'Logs']
    EXPECTED_VAULT_NAME    = 'AI_Employee_Vault'

    def __init__(
        self,
        vault_path: str,
        check_interval: int = 60,
        ai_agent: str = 'qwen',
        watch_mode: bool = False
    ):
        # Resolve and validate the vault path before anything else
        self.vault_path     = self._resolve_vault_path(vault_path)
        self.check_interval = check_interval
        self.ai_agent       = ai_agent
        self.watch_mode     = watch_mode

        # ── Define all vault sub-folder paths ───────────────────────────────
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

        # Create all folders if they don't already exist
        for folder in [
            self.inbox, self.needs_action, self.done, self.plans,
            self.pending_approval, self.approved, self.rejected,
            self.logs, self.accounting, self.briefings, self.drop,
            self.processing, self.failed,
        ]:
            folder.mkdir(parents=True, exist_ok=True)

        self._setup_logging()

        # Track files currently being processed to prevent concurrent double-processing
        self.processing_files: Set[str] = set()
        # Track start times per file so we can report elapsed duration
        self.processing_times: Dict[str, float] = {}

        # Check once at startup whether the chosen AI agent is reachable
        self.ai_available = self._check_ai_agent()

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

    # ── Main run loop ─────────────────────────────────────────────────────────

    def run(self) -> None:
        """Entry point — print startup banner then hand off to run mode."""
        agent_status = 'available' if self.ai_available else 'unavailable'
        mode_text = 'watch' if self.watch_mode else 'polling'

        print_header("🤖 AI EMPLOYEE ORCHESTRATOR v0.1")
        
        print_info("Vault", str(self.vault_path))
        print_info("AI Agent", f"{self.ai_agent} ({agent_status})")
        print_info("Mode", f"{mode_text} · Interval: {self.check_interval}s")
        print_info("Flow", "Inbox → Processing → Done/Failed")
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

        class InboxHandler(FileSystemEventHandler):  # type: ignore
            def __init__(self, orchestrator):
                self.orchestrator = orchestrator

            def on_created(self, event):
                if not event.is_directory and Path(event.src_path).suffix.lower() == '.md':
                    self.orchestrator._print_file_detected(Path(event.src_path).name)
                    self.orchestrator._process_inbox()
                    self.orchestrator._update_dashboard()

            def on_modified(self, event):
                pass

        observer = None
        try:
            observer = Observer()  # type: ignore
            observer.schedule(InboxHandler(self), str(self.inbox), recursive=False)
            observer.start()

            print(f"  👁️ MONITORING ACTIVE")
            print(f"     Watching: {self.inbox}")
            print(f"     Interval: {self.check_interval}s (heartbeat)")
            print(f"     Press Ctrl+C to stop\n")

            self._process_inbox()
            self._process_approved()
            self._update_dashboard()

            while True:
                time.sleep(self.check_interval)
                self._update_dashboard()

        except KeyboardInterrupt:
            print(f"\n  ⏹️ Stopped by user")
            if observer:
                observer.stop()
        finally:
            if observer and WATCHDOG_AVAILABLE:
                observer.stop()
                observer.join()

    def _run_polling_mode(self) -> None:
        """Polling mode — scans Inbox/ every check_interval seconds."""
        print(f"  🔍 SCANNING ACTIVE")
        print(f"     Target: {self.inbox}")
        print(f"     Interval: Every {self.check_interval} seconds")
        print(f"     Press Ctrl+C to stop\n")

        last_detected_files: set = set()

        try:
            while True:
                try:
                    current_files = {f.name for f in self.inbox.iterdir() if f.suffix.lower() == '.md'}
                    new_files = current_files - last_detected_files
                    
                    if new_files:
                        for filename in new_files:
                            print_task_detected(filename)
                        print(f"\n  ➡ Processing {len(new_files)} file(s)...")
                    else:
                        print(f"\n  ➡ No new files found")
                        print(f"  ➡ Waiting {self.check_interval} seconds...")

                    self._process_inbox()
                    self._process_approved()
                    self._update_dashboard()
                    last_detected_files = current_files

                except Exception as e:
                    self.logger.error(f'Error in main loop: {e}', exc_info=True)

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            print(f"\n  ⏹️ Stopped by user")

    # ── Console output helpers ────────────────────────────────────────────────

    def _print_file_detected(self, filename: str) -> None:
        """Print a notification when a new file is detected."""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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

    def _process_needs_action(self) -> None:
        """Process files in Needs_Action/."""
        try:
            needs_action_files = [
                f for f in self.needs_action.iterdir()
                if f.suffix.lower() == '.md' and f.name not in self.processing_files
            ]
            if needs_action_files:
                self.logger.info(f'Found {len(needs_action_files)} item(s) in Needs_Action')
            for action_file in needs_action_files:
                self._stage_and_process_file(action_file)
        except Exception as e:
            self.logger.error(f'Error processing Needs_Action: {e}', exc_info=True)

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
        return f'''You are the AI Employee v0.1. Process this file.

File: {filename}

Content:
{content}

Tasks:
1. Read and understand the file
2. Create plan at: {plan_path}
3. Execute actions following Company Handbook rules
4. Move file to /Done when complete
5. Update Dashboard.md

Start by creating a plan.'''

    def _process_with_qwen(self, staging_file: Path, plan_file: Path, content: str, prompt: str, start_time: float) -> None:
        """Qwen Code processing path."""
        self.logger.info(f'Processing with Qwen: {staging_file.name}')

        plan_file.write_text(
            f'---\ncreated: {datetime.now().isoformat()}\nstatus: active\nsource_file: {staging_file.name}\nai_agent: qwen\n---\n\n# Plan: Process {staging_file.name}\n',
            encoding='utf-8'
        )
        self.logger.info(f'Plan created: {plan_file.name}')

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

    def _move_to_folder(self, source_file: Path, dest_folder: Path, new_status: str = None) -> Path:  # type: ignore
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

    def _move_to_failed(self, source_file: Path, error_message: str, start_time: float = None) -> None:  # type: ignore
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

    # ── Approved actions ──────────────────────────────────────────────────────

    def _process_approved(self) -> None:
        """Process all files in Approved/."""
        try:
            approved_files = [f for f in self.approved.iterdir() if f.suffix.lower() == '.md']
            if not approved_files:
                return
            self.logger.info(f'Found {len(approved_files)} approved item(s)')
            for approved_file in approved_files:
                self._execute_approved_action(approved_file)
        except Exception as e:
            self.logger.error(f'Error processing Approved: {e}')

    def _execute_approved_action(self, approved_file: Path) -> None:
        """Execute approved action."""
        try:
            self._move_to_folder(approved_file, self.done, 'approved')
        except Exception as e:
            self.logger.error(f'Error executing approved action: {e}')

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
                        active_projects.append({
                            'file': plan_file.name,
                            'last_modified': mtime
                        })
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f'Error scanning Plans: {e}')
        return active_projects

    def _update_dashboard_section(self, content: str, section_name: str, new_content: str) -> str:
        """Update a specific section in the dashboard."""
        lines = content.split('\n')
        in_target_section = False
        new_lines = []
        
        for i, line in enumerate(lines):
            if section_name in line and line.strip().startswith('##'):
                in_target_section = True
                new_lines.append(line)
                continue
                
            if in_target_section and line.strip().startswith('##') and section_name not in line:
                in_target_section = False
                
            if in_target_section and line.strip() == '---':
                new_lines.append(line)
                new_lines.append(new_content)
                skip_until_next = True
                j = i + 1
                while j < len(lines):
                    if lines[j].strip() == '---':
                        new_lines.append(lines[j])
                        i = j
                        break
                    j += 1
                in_target_section = False
                continue
                
            new_lines.append(line)
            
        return '\n'.join(new_lines)

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
        """Update the Active Projects section with real data."""
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

    # ── Status snapshot ───────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Return a snapshot dict of current orchestrator state for monitoring/debugging."""
        return {
            'vault_path':       str(self.vault_path),
            'ai_agent':         self.ai_agent,
            'ai_available':     self.ai_available,
            'watch_mode':       self.watch_mode,
            'folders': {
                'inbox':            sum(1 for f in self.inbox.iterdir()            if f.suffix.lower() == '.md'),
                'processing':       sum(1 for f in self.processing.iterdir()       if f.suffix.lower() == '.md'),
                'needs_action':     sum(1 for f in self.needs_action.iterdir()     if f.suffix.lower() == '.md'),
                'pending_approval': sum(1 for f in self.pending_approval.iterdir() if f.suffix.lower() == '.md'),
                'approved':         sum(1 for f in self.approved.iterdir()         if f.suffix.lower() == '.md'),
                'done':             sum(1 for f in self.done.iterdir()             if f.suffix.lower() == '.md'),
                'failed':           sum(1 for f in self.failed.iterdir()           if f.suffix.lower() == '.md'),
            },
            'processing_files': list(self.processing_files),
            'active_projects':  len(self._get_active_projects()),
        }


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description='AI Employee Orchestrator')
    parser.add_argument('--vault', '-v', required=True, help='Path to the Obsidian vault')
    parser.add_argument('--interval', '-i', type=int, default=60, help='Check interval in seconds (default: 60)')
    parser.add_argument('--ai-agent', '-a', default='qwen', choices=['qwen', 'claude'], help='AI agent (default: qwen)')
    parser.add_argument('--watch', '-w', action='store_true', help='Enable real-time watchdog monitoring')

    args = parser.parse_args()

    Orchestrator(
        vault_path=args.vault,
        check_interval=args.interval,
        ai_agent=args.ai_agent,
        watch_mode=args.watch,
    ).run()


if __name__ == '__main__':
    main()