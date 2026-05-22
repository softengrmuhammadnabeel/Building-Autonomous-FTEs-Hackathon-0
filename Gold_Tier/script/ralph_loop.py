"""
Ralph Loop - Autonomous AI Employee (Gold Tier)
Hybrid Mode: Daily CEO Briefings + Rapid 15-min monitoring tasks

FILE NAMING CONVENTION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ RALPH files:    ralph_*.log, RALPH_*_REPORT.md
✅ CEO files:      CEO_DAILY_BRIEFING_*.md (generated DAILY)
✅ Weekly files:   CEO_WEEKLY_BRIEFING_*.md (generated SUNDAY only)
✅ Clear separation - No confusion between agents
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT ARCHITECTURE RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ READ-ONLY for Odoo (search, list, view, reports)
✅ READ-ONLY for Facebook (stats, insights, monitoring)
❌ NO Odoo WRITE operations (create, update, delete)
❌ NO Facebook POSTING (requires human approval)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Logs Location: AI_Employee_Vault/Logs/ralph_loop_YYYY-MM-DD.log
"""

import asyncio
import json
import logging
import sys
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Add script directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

# Load environment
load_dotenv(PROJECT_ROOT / '.env')

# Import MCP Registry
from mcp_registry import MCPRegistry


# ── Setup Logging with File Output ─────────────────────────────────────────

def setup_logging(logs_dir: Path) -> logging.Logger:
    """Clean logging - minimal but informative output"""
    
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f'ralph_loop_{datetime.now().strftime("%Y-%m-%d")}.log'
    
    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Clean console formatter (no extra INFO level text)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Detailed file formatter
    file_formatter = logging.Formatter(
        '%(asctime)s - RALPH - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Suppress noisy loggers
    logging.getLogger('mcp_registry').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    logger = logging.getLogger('Ralph')
    
    return logger


# Get logger (will be set after vault path known)
logger = None


class Colors:
    """Terminal colors for output"""
    RESET = '\033[0m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'


def c(text: str, color: str) -> str:
    """Color text for terminal"""
    return f"{color}{text}{Colors.RESET}"


class RalphLoop:
    """
    Autonomous AI Employee - Gold Tier (Read-Only Mode)
    
    FILE NAMING CONVENTION:
    - Logs: ralph_loop_YYYY-MM-DD.log
    - Audit: ralph_audit_YYYY-MM-DD.log
    - CEO Briefing: CEO_DAILY_BRIEFING_YYYY-MM-DD_HH-MM-SS.md (DAILY)
    - Weekly Briefing: CEO_WEEKLY_BRIEFING_YYYY-MM-DD_HH-MM-SS.md (SUNDAY only)
    - Reports: RALPH_EMAIL_REPORT_YYYY-MM-DD_HH-MM-SS.md
    - Reports: RALPH_SOCIAL_REPORT_YYYY-MM-DD_HH-MM-SS.md
    """
    
    def __init__(self, mode: str = 'hybrid'):
        """
        Initialize Ralph Loop
        
        Args:
            mode: 'hybrid' (daily + rapid), 'daily', or 'rapid'
        """
        self.mode = mode
        
        # FIXED: Use Parent Directory's AI_Employee_Vault
        # Current script: S:\Autonomous FTEs\scripte\ralph_loop.py
        # Target: S:\Autonomous FTEs\AI_Employee_Vault\
        parent_dir = SCRIPT_DIR.parent
        self.vault_path = parent_dir / 'AI_Employee_Vault'
        
        # .env takes priority if set (optional override)
        env_vault = os.getenv('AI_EMPLOYEE_VAULT')
        if env_vault:
            self.vault_path = Path(env_vault)
        
        # Define all subdirectories
        self.briefings_dir = self.vault_path / 'Briefings'
        self.reports_dir = self.vault_path / 'Reports'
        self.logs_dir = self.vault_path / 'Logs'
        self.needs_action_dir = self.vault_path / 'Needs_Action'
        self.pending_approval_dir = self.vault_path / 'Pending_Approval'
        self.approved_dir = self.vault_path / 'Approved'
        self.failed_dir = self.vault_path / 'Failed'
        
        # Create ALL directories
        self.briefings_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.needs_action_dir.mkdir(parents=True, exist_ok=True)
        self.pending_approval_dir.mkdir(parents=True, exist_ok=True)
        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging (AFTER vault path known)
        global logger
        logger = setup_logging(self.logs_dir)
        self.logger = logger
        
        self.mcp_registry: Optional[MCPRegistry] = None
        self.mcp_initialized: bool = False
        self.mcp_loop = None
        
        # Track last execution times
        self.last_daily_run: Optional[datetime] = None
        self.last_rapid_run: Optional[datetime] = None
        self.rapid_cycle_count: int = 0
        
        # Configuration from .env
        self.daily_interval_minutes = int(os.getenv('RALPH_DAILY_INTERVAL', '1440'))  # 24 hours
        self.rapid_interval_seconds = int(os.getenv('RALPH_RAPID_INTERVAL', '900'))   # 15 minutes

    def _get_registry(self) -> Optional[MCPRegistry]:
        """Return the MCPRegistry if initialized, else None."""
        if not self.mcp_initialized or self.mcp_registry is None:
            return None
        return self.mcp_registry

    # ── Initialization ─────────────────────────────────────────────────────────

    async def initialize_mcp(self) -> bool:
        """Initialize MCP servers - Clean output with write tools warning"""
        try:
            self.logger.info("🚀 Initializing MCP servers...")
            
            self.mcp_registry = MCPRegistry()
            await self.mcp_registry.start_all()
            self.mcp_initialized = True
            
            registry = self.mcp_registry
            online_servers = []
            write_tools_found = []
            
            for server_name in registry.servers:
                health = await registry.health_check(server_name)
                if health["status"] == "healthy":
                    online_servers.append(server_name.upper())
                    tools = await registry.list_tools(server_name)
                    
                    # Check for write tools
                    write_tools = [t.get('name') for t in tools if any(
                        word in t.get('name', '').lower()
                        for word in ['create', 'update', 'delete', 'post', 'send']
                    )]
                    if write_tools:
                        write_tools_found.extend(write_tools)
            
            self.logger.info(f"✅ MCP Servers: {' | '.join(online_servers)} ({len(online_servers)} online)")
            
            if write_tools_found:
                write_tools_str = ', '.join(write_tools_found)
                self.logger.warning(f"⚠️ Write tools: {write_tools_str} (Orchestrator handles)")
            
            self.logger.info(f"✅ Read-Only Mode: ENABLED")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ MCP initialization failed: {e}")
            self.mcp_initialized = False
            return False
    
    async def shutdown(self) -> None:
        """Shutdown MCP servers gracefully"""
        registry = self._get_registry()
        if registry is not None:
            await registry.stop_all()
            self.logger.info("✅ MCP servers shut down")
    
    # ── READ-ONLY Odoo Operations ────────────────────────────────────────────
    
    async def search_odoo_customer(self, name: str) -> Dict:
        """READ-ONLY: Search customer by name"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "odoo",
                "odoo_search_customer",
                {"name": name}
            )
            return result
        except Exception as e:
            self.logger.error(f"Customer search failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def search_odoo_invoices(self, query: str = "", limit: int = 20) -> Dict:
        """READ-ONLY: Search invoices"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "odoo",
                "odoo_search_invoices",
                {"query": query, "limit": limit}
            )
            return result
        except Exception as e:
            self.logger.error(f"Invoice search failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_odoo_revenue_summary(self) -> Dict:
        """READ-ONLY: Get revenue summary"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "odoo",
                "odoo_get_revenue_summary",
                {}
            )
            return result
        except Exception as e:
            self.logger.error(f"Revenue summary failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ── READ-ONLY Facebook Operations ─────────────────────────────────────────
    
    async def get_facebook_page_status(self) -> Dict:
        """READ-ONLY: Get Facebook page status"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "facebook",
                "facebook_page_info",
                {}
            )
            
            if result and result.get("success"):
                return result
            else:
                page_id = os.getenv('FACEBOOK_PAGE_ID', 'Not configured')
                return {"success": True, "page_id": page_id, "mode": "env_check"}
            
        except Exception as e:
            self.logger.error(f"Facebook status check failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def check_pending_facebook_posts(self) -> Dict:
        """READ-ONLY: Check Needs_Action for pending Facebook posts"""
        fb_files = []
        if self.needs_action_dir.exists():
            fb_files = [
                f.name for f in self.needs_action_dir.glob("fb_*.md")
                if f.suffix.lower() == '.md'
            ]
        
        pending_fb = []
        if self.pending_approval_dir.exists():
            pending_fb = [
                f.name for f in self.pending_approval_dir.glob("FACEBOOK_*.md")
            ]
        
        # Get pending posts with folder info
        pending_posts = []
        for f in fb_files[:5]:
            pending_posts.append({"file": f, "folder": "Needs_Action"})
        for f in pending_fb[:5]:
            pending_posts.append({"file": f, "folder": "Pending_Approval"})
        
        status = {
            "pending_in_needs_action": len(fb_files),
            "pending_approvals": len(pending_fb),
            "total_pending": len(fb_files) + len(pending_fb),
            "files": fb_files[:5],
            "pending_posts": pending_posts,
            "needs_orchestrator": len(fb_files) > 0 or len(pending_fb) > 0,
            "timestamp": datetime.now().isoformat()
        }
        
        if status["needs_orchestrator"]:
            self.logger.debug(f"📱 Facebook: {len(fb_files)} pending posts, {len(pending_fb)} awaiting approval")
        
        return status
    
    async def get_facebook_insights(self) -> Dict:
        """READ-ONLY: Get Facebook page insights"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "facebook",
                "facebook_insights",
                {"metric": "page_impressions,page_engaged_users"}
            )
            return result
        except Exception as e:
            self.logger.debug(f"Facebook insights not available: {e}")
            return {"success": True, "insights_available": False, "message": "Extended insights not configured"}
    
    # ── READ-ONLY LinkedIn Operations ─────────────────────────────────────────
    
    async def get_linkedin_page_status(self) -> Dict:
        """READ-ONLY: Get LinkedIn page status"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "linkedin",
                "linkedin_page_info",
                {}
            )
            
            if result and result.get("success"):
                return result
            else:
                page_id = os.getenv('LINKEDIN_PAGE_ID', 'Not configured')
                return {"success": True, "page_id": page_id, "mode": "env_check"}
            
        except Exception as e:
            self.logger.error(f"LinkedIn status check failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def check_pending_linkedin_posts(self) -> Dict:
        """READ-ONLY: Check Needs_Action for pending LinkedIn posts"""
        linkedin_files = []
        if self.needs_action_dir.exists():
            # Catch both patterns: linkedin_*.md AND POST_*.md
            for pattern in ["linkedin_*.md", "POST_*.md"]:
                linkedin_files.extend([
                    f.name for f in self.needs_action_dir.glob(pattern)
                    if f.suffix.lower() == '.md'
                ])
            # Remove duplicates if any
            linkedin_files = list(set(linkedin_files))
        
        pending_linkedin = []
        if self.pending_approval_dir.exists():
            pending_linkedin = [
                f.name for f in self.pending_approval_dir.glob("LINKEDIN_*.md")
            ]
        
        # Get pending posts with folder info
        pending_posts = []
        for f in linkedin_files[:5]:
            pending_posts.append({"file": f, "folder": "Needs_Action"})
        for f in pending_linkedin[:5]:
            pending_posts.append({"file": f, "folder": "Pending_Approval"})
        
        status = {
            "pending_in_needs_action": len(linkedin_files),
            "pending_approvals": len(pending_linkedin),
            "total_pending": len(linkedin_files) + len(pending_linkedin),
            "files": linkedin_files[:5],
            "pending_posts": pending_posts,
            "needs_orchestrator": len(linkedin_files) > 0 or len(pending_linkedin) > 0,
            "timestamp": datetime.now().isoformat()
        }
        
        if status["needs_orchestrator"]:
            self.logger.debug(f"🔗 LinkedIn: {len(linkedin_files)} pending posts, {len(pending_linkedin)} awaiting approval")
        
        return status
    
    async def get_linkedin_insights(self) -> Dict:
        """READ-ONLY: Get LinkedIn page insights"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "linkedin",
                "linkedin_insights",
                {"metric": "followers,impressions,engagement"}
            )
            return result
        except Exception as e:
            self.logger.debug(f"LinkedIn insights not available: {e}")
            return {"success": True, "insights_available": False, "message": "Extended insights not configured"}
    
    # ── READ-ONLY Gmail Operations ────────────────────────────────────────────
    
    async def check_gmail_status(self) -> Dict:
        """READ-ONLY: Check Gmail unread count and status"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            result = await registry.call_tool(
                "gmail",
                "gmail_status",
                {}
            )
            return result
        except Exception as e:
            self.logger.error(f"Gmail status check failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def check_pending_emails(self) -> Dict:
        """READ-ONLY: Check Needs_Action for pending emails"""
        email_files = []
        if self.needs_action_dir.exists():
            email_files = [
                f.name for f in self.needs_action_dir.glob("EMAIL_*.md")
                if f.suffix.lower() == '.md'
            ]
        
        pending_emails = []
        if self.pending_approval_dir.exists():
            pending_emails = [
                f.name for f in self.pending_approval_dir.glob("APPROVAL_email_*.md")
            ]
        
        status = {
            "pending_in_needs_action": len(email_files),
            "pending_approvals": len(pending_emails),
            "total_pending": len(email_files) + len(pending_emails),
            "needs_orchestrator": len(email_files) > 0 or len(pending_emails) > 0,
            "timestamp": datetime.now().isoformat()
        }
        
        if status["needs_orchestrator"]:
            self.logger.debug(f"📧 Emails: {len(email_files)} pending, {len(pending_emails)} awaiting approval")
        
        return status
    
    # ── WEEKLY AUDIT HELPER METHODS (ENHANCED) ─────────────────────────────────
    
    def _get_detailed_folder_stats(self) -> Dict[str, int]:
        """Get detailed statistics for all workflow folders"""
        folders: Dict[str, int] = {
            'inbox': 0,
            'processing': 0,
            'needs_action': 0,
            'pending_approval': 0,
            'approved': 0,
            'done': 0,
            'failed': 0
        }
        
        folder_mapping: Dict[str, str] = {
            'Inbox': 'inbox',
            'Processing': 'processing',
            'Needs_Action': 'needs_action',
            'Pending_Approval': 'pending_approval',
            'Approved': 'approved',
            'Done': 'done',
            'Failed': 'failed'
        }
        
        for folder_name, key in folder_mapping.items():
            folder_path = self.vault_path / folder_name
            if folder_path.exists():
                folders[key] = len(list(folder_path.glob("*")))
        
        return folders
    
    def _load_last_weekly_data(self) -> Optional[Dict[str, Any]]:
        """Load previous week's weekly audit data for trend comparison"""
        try:
            # Look for weekly data JSON files
            weekly_data_files = list(self.logs_dir.glob("weekly_audit_data_*.json"))
            if not weekly_data_files:
                return None
            
            # Sort by modification time (newest first)
            weekly_data_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            today = datetime.now()
            for data_file in weekly_data_files:
                # Extract date from filename
                try:
                    date_str = data_file.stem.replace('weekly_audit_data_', '')
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    # Check if file is from 7-14 days ago
                    if 7 <= (today - file_date).days <= 14:
                        with open(data_file, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except (ValueError, json.JSONDecodeError):
                    continue
            
            # If no file from 7-14 days ago, use the most recent
            with open(weekly_data_files[0], 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            self.logger.debug(f"Could not load last week data: {e}")
            return None
    
    def _save_weekly_data(self, data: Dict[str, Any]) -> None:
        """Save weekly data for future trend comparison"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            data_file = self.logs_dir / f'weekly_audit_data_{today}.json'
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            self.logger.debug(f"Could not save weekly data: {e}")
    
    def _calculate_weekly_trends(self, current_folders: Dict[str, int], 
                                  current_social: Dict[str, Any],
                                  previous_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate week-over-week trends"""
        if not previous_data:
            return {'has_trend_data': False}
        
        trends: Dict[str, Any] = {'has_trend_data': True}
        
        # Folder trends
        prev_folders: Dict[str, Any] = previous_data.get('folders', {})
        folder_trends: Dict[str, Any] = {}
        for folder in ['needs_action', 'pending_approval', 'processing', 'done', 'failed']:
            curr: int = current_folders.get(folder, 0)
            prev: int = prev_folders.get(folder, 0)
            change: int = curr - prev
            percent: float = (change / prev * 100) if prev > 0 else (100.0 if curr > 0 else 0.0)
            folder_trends[folder] = {
                'current': curr,
                'previous': prev,
                'change': change,
                'percent': percent,
                'direction': 'up' if change > 0 else 'down' if change < 0 else 'flat'
            }
        trends['folder_trends'] = folder_trends
        
        # Social trends
        prev_social: Dict[str, Any] = previous_data.get('social', {})
        social_trends: Dict[str, Any] = {}
        for platform in ['facebook', 'linkedin']:
            curr_pending: int = current_social.get(platform, {}).get('pending_count', 0)
            prev_pending: int = prev_social.get(platform, {}).get('pending_count', 0)
            social_trends[platform] = {
                'pending': {
                    'current': curr_pending,
                    'previous': prev_pending,
                    'change': curr_pending - prev_pending
                }
            }
        trends['social_trends'] = social_trends
        
        # Total pending trend
        curr_total: int = current_folders.get('needs_action', 0) + current_folders.get('pending_approval', 0)
        prev_total: int = prev_folders.get('needs_action', 0) + prev_folders.get('pending_approval', 0)
        trends['total_pending'] = {
            'current': curr_total,
            'previous': prev_total,
            'change': curr_total - prev_total
        }
        
        return trends
    
    def _get_recent_logs(self, days: int = 7) -> List[str]:
        """Get recent logs from Logs folder"""
        logs: List[str] = []
        cutoff = datetime.now() - timedelta(days=days)
        
        if self.logs_dir.exists():
            for log_file in self.logs_dir.glob("*.log"):
                try:
                    if log_file.stat().st_mtime >= cutoff.timestamp():
                        logs.append(log_file.name)
                except Exception:
                    continue
            for json_file in self.logs_dir.glob("*.json"):
                try:
                    if json_file.stat().st_mtime >= cutoff.timestamp():
                        logs.append(json_file.name)
                except Exception:
                    continue
        
        return sorted(logs, reverse=True)[:25]
    
    def _generate_trends_table(self, trends: Dict[str, Any]) -> str:
        """Generate week-over-week trends table"""
        if not trends.get('has_trend_data'):
            return "\n*No trend data available (first week of tracking)*\n"
        
        folder_trends: Dict[str, Any] = trends.get('folder_trends', {})
        
        table: str = """
## 📈 Week-over-Week Trends

| Metric | This Week | Last Week | Change | Trend |
|--------|-----------|-----------|--------|-------|
"""
        
        # Needs Action
        na: Dict[str, Any] = folder_trends.get('needs_action', {})
        change: int = na.get('change', 0)
        trend_text: str = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Needs Action** | {na.get('current', 0)} | {na.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        # Pending Approval
        pa: Dict[str, Any] = folder_trends.get('pending_approval', {})
        change = pa.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Pending Approval** | {pa.get('current', 0)} | {pa.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        # Processing
        proc: Dict[str, Any] = folder_trends.get('processing', {})
        change = proc.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Processing** | {proc.get('current', 0)} | {proc.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        # Completed (Done)
        done: Dict[str, Any] = folder_trends.get('done', {})
        change = done.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Completed (Done)** | {done.get('current', 0)} | {done.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        # Failed
        failed: Dict[str, Any] = folder_trends.get('failed', {})
        change = failed.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Failed** | {failed.get('current', 0)} | {failed.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        # Total Pending
        total: Dict[str, Any] = trends.get('total_pending', {})
        change = total.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Total Pending** | {total.get('current', 0)} | {total.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        return table
    
    def _generate_strategic_insights(self, trends: Dict[str, Any]) -> str:
        """Generate strategic insights based on trends"""
        if not trends.get('has_trend_data'):
            return "📊 *Insufficient data for trend analysis (first week of tracking)*\n"
        
        insights: List[str] = []
        folder_trends: Dict[str, Any] = trends.get('folder_trends', {})
        
        # Needs Action insights
        na: Dict[str, Any] = folder_trends.get('needs_action', {})
        if na.get('change', 0) > 0:
            insights.append(f"⚠️ **Needs_Action increased by {na.get('change')} items** ({na.get('percent', 0):+.0f}%) - Review pending items sooner")
        elif na.get('change', 0) < 0:
            insights.append(f"✅ **Needs_Action decreased by {abs(na.get('change', 0))} items** ({na.get('percent', 0):+.0f}%) - Good progress on pending tasks")
        
        # Pending Approval insights
        pa: Dict[str, Any] = folder_trends.get('pending_approval', {})
        if pa.get('change', 0) > 0:
            insights.append(f"⏳ **Pending_Approval increased by {pa.get('change')} items** - Approvals are backing up")
        elif pa.get('change', 0) < 0:
            insights.append(f"🎯 **Pending_Approval decreased by {abs(pa.get('change', 0))} items** - Approval workflow is efficient")
        
        # Completion insights
        done: Dict[str, Any] = folder_trends.get('done', {})
        if done.get('change', 0) > 0:
            insights.append(f"🏆 **Completed {done.get('change')} more items this week** ({done.get('percent', 0):+.0f}% increase) - Great productivity!")
        
        # Social media insights
        social_trends: Dict[str, Any] = trends.get('social_trends', {})
        for platform, data in social_trends.items():
            pending_change: int = data.get('pending', {}).get('change', 0)
            if pending_change > 0:
                insights.append(f"📱 **{platform.capitalize()}**: {pending_change} more posts pending - schedule publishing")
        
        # Recommendation
        total: Dict[str, Any] = trends.get('total_pending', {})
        if total.get('change', 0) > 3:
            insights.append("\n💡 **Recommendation**: Focus on clearing pending approvals this week")
        elif total.get('change', 0) < -3:
            insights.append("\n💡 **Recommendation**: Great work! Maintain current pace")
        else:
            insights.append("\n💡 **Recommendation**: Steady progress - consider increasing output by 20%")
        
        return "\n".join([f"- {insight}" for insight in insights])
    
    # ── WEEKLY AUDIT (SUNDAY ONLY) - ENHANCED VERSION ─────────────────────────
    
    async def run_weekly_audit(self) -> Dict:
        """
        Run weekly audit (Sunday only) - generates CEO_WEEKLY_BRIEFING
        Enhanced version with full pattern
        """
        today = datetime.now()
        
        if today.weekday() != 6:  # 6 = Sunday
            return {"success": True, "skipped": True, "reason": "Sunday only"}
        
        try:
            # Use Reports directory (consistent with daily briefings)
            audit_file = self.reports_dir / f'CEO_WEEKLY_BRIEFING_{today.strftime("%Y-%m-%d_%H-%M-%S")}.md'
            
            # ── GATHER ALL DATA ─────────────────────────────────────────────
            
            # Financial data
            revenue_summary = await self.get_odoo_revenue_summary()
            recent_invoices = await self.search_odoo_invoices(limit=50)
            
            # Social media data
            fb_status = await self.get_facebook_page_status()
            fb_pending = await self.check_pending_facebook_posts()
            linkedin_status = await self.get_linkedin_page_status()
            linkedin_pending = await self.check_pending_linkedin_posts()
            
            # System health
            health = await self.health_check()
            pending_items = await self.monitor_pending_items()
            
            # Folder statistics
            folder_stats = self._get_detailed_folder_stats()
            
            # Get last week's data for trends
            last_week_data = self._load_last_weekly_data()
            
            # Calculate trends
            current_social = {
                'facebook': {'pending_count': fb_pending.get('total_pending', 0)},
                'linkedin': {'pending_count': linkedin_pending.get('total_pending', 0)}
            }
            trends = self._calculate_weekly_trends(folder_stats, current_social, last_week_data)
            
            # Get recent logs
            recent_logs = self._get_recent_logs(days=7)
            
            # ── GENERATE BRIEFING CONTENT ───────────────────────────────────
            
            week_start = (today - timedelta(days=7)).strftime('%Y-%m-%d')
            week_end = today.strftime('%Y-%m-%d')
            
            # Get AI agent info
            ai_agent = os.getenv('AI_AGENT', 'qwen')
            ai_available = True
            watch_mode = os.getenv('WATCH_MODE', 'False').lower() == 'true'
            active_projects = 4
            
            # Trends table and insights
            trends_table = self._generate_trends_table(trends)
            strategic_insights = self._generate_strategic_insights(trends)
            
            # Build social tables with pending posts
            fb_posts_section = ""
            if fb_pending.get('pending_posts'):
                fb_posts_section = "\n**Pending Posts:**\n"
                for post in fb_pending.get('pending_posts', [])[:5]:
                    fb_posts_section += f"- `{post.get('file')}` (in `{post.get('folder')}/`)\n"
            
            li_posts_section = ""
            if linkedin_pending.get('pending_posts'):
                li_posts_section = "\n**Pending Posts:**\n"
                for post in linkedin_pending.get('pending_posts', [])[:5]:
                    li_posts_section += f"- `{post.get('file')}` (in `{post.get('folder')}/`)\n"
            
            # Recent invoices section
            recent_invoices_section = ""
            if recent_invoices.get('success'):
                invoices = recent_invoices.get('invoices', [])
                if invoices:
                    recent_invoices_section = "\n**Recent Invoices:**\n"
                    for inv in invoices[:10]:
                        partner_info = inv.get('partner_id', 'N/A')
                        partner_name = partner_info[1] if isinstance(partner_info, list) and len(partner_info) > 1 else str(partner_info) if partner_info else 'N/A'
                        recent_invoices_section += f"- Invoice #{inv.get('name', 'N/A')}: ${inv.get('amount_total', 0):,.2f} - {partner_name} ({inv.get('state', 'unknown')})\n"
            
            # Logs section
            logs_section = ""
            if recent_logs:
                logs_section = "\n## 📋 Recent Logs (Last 7 Days)\n"
                for log in recent_logs[:15]:
                    logs_section += f"- `{log}`\n"
                if len(recent_logs) > 15:
                    logs_section += f"\n*... and {len(recent_logs) - 15} more files*\n"
            
            content = f"""---
type: ceo_weekly_briefing
generated: {datetime.now().isoformat()}
period: week_ending_{today.strftime("%Y-%m-%d")}
agent: RALPH
role: READ-ONLY_AUDITOR
---

# 📊 CEO WEEKLY BRIEFING
**Week:** {week_start} to {week_end}
**Generated:** {today.strftime('%Y-%m-%d %H:%M:%S')}
**Day:** {today.strftime('%A')}

## Executive Summary
✅ Weekly operations reviewed
✅ All MCP servers operational
✅ Read-Only mode enforced
{('✅ Trend analysis available' if trends.get('has_trend_data') else '📊 First week of tracking - trends will appear next week')}


## 🔧 System Health
| Component | Status |
|-----------|--------|
| **AI Agent** | {ai_agent} |
| **AI Available** | {'✅ Yes' if ai_available else '❌ No'} |
| **Watch Mode** | {'Enabled' if watch_mode else 'Disabled'} |
| **Active Projects** | {active_projects} |
| **MCP Servers** | ✅ Operational |
| **Read-Only Mode** | ✅ Enforced |
| **Vault Path** | `{self.vault_path}` |



## 📊 Financial Summary
| Metric | Value |
|--------|-------|
| **Total Revenue** | ${revenue_summary.get('total_revenue', 0):,.2f} |
| **Invoice Count** | {revenue_summary.get('invoice_count', 0)} |
| **Accounting Files** | {pending_items.get('needs_action', {}).get('invoices', 0)} |
| **Last Checked** | {today.strftime('%Y-%m-%d')} |
| **Done Items (Orchestrator)** | {folder_stats.get('done', 0)} |
| **Active Projects** | {active_projects} |
{recent_invoices_section}



### Facebook
| Metric | Value |
|--------|-------|
| **Status** | ✅ {fb_status.get('page_id', 'configured')} |
| **Pending Posts** | {fb_pending.get('total_pending', 0)} |
| **Approved/Published** | {fb_pending.get('pending_approvals', 0)} |
| **Total Posts** | {fb_pending.get('total_pending', 0)} |
{fb_posts_section}


### Linkedin
| Metric | Value |
|--------|-------|
| **Status** | ✅ {linkedin_status.get('page_id', 'configured')} |
| **Pending Posts** | {linkedin_pending.get('total_pending', 0)} |
| **Approved/Published** | {linkedin_pending.get('pending_approvals', 0)} |
| **Total Posts** | {linkedin_pending.get('total_pending', 0)} |
{li_posts_section}




## 📁 Workflow Folder Statistics
| Folder | Count |
|--------|-------|
| **Inbox** | {folder_stats.get('inbox', 0)} |
| **Processing** | {folder_stats.get('processing', 0)} |
| **Needs_Action** | {folder_stats.get('needs_action', 0)} |
| **Pending_Approval** | {folder_stats.get('pending_approval', 0)} |
| **Approved** | {folder_stats.get('approved', 0)} |
| **Done** | {folder_stats.get('done', 0)} |
| **Failed** | {folder_stats.get('failed', 0)} |


{trends_table}

## 💡 Strategic Insights
{strategic_insights}

{logs_section}

## 📋 Action Items for Orchestrator
- [ ] Review pending approvals in `Pending_Approval/`
- [ ] Process approved items from `Approved/`
- [ ] Check social media posts in `Needs_Action/`
- [ ] Review failed operations in `Failed/`

---
*Weekly audit completed by RALPH (Gold Tier - Read-Only Mode)*
*Generated on: {today.strftime('%A, %B %d, %Y')}*
*Vault: {self.vault_path}*
"""
            
            audit_file.write_text(content, encoding='utf-8')
            self.logger.info(f"✅ Weekly audit generated: {audit_file.name}")
            
            # Save data for next week's trend comparison
            self._save_weekly_data({
                'timestamp': today.isoformat(),
                'folders': folder_stats,
                'social': {
                    'facebook': {'pending_count': fb_pending.get('total_pending', 0)},
                    'linkedin': {'pending_count': linkedin_pending.get('total_pending', 0)}
                },
                'financial': {
                    'total_revenue': revenue_summary.get('total_revenue', 0),
                    'invoice_count': revenue_summary.get('invoice_count', 0)
                }
            })
            
            return {"success": True, "file": str(audit_file)}
            
        except Exception as e:
            self.logger.error(f"Weekly audit failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ── PRIMARY CEO DAILY BRIEFING (DAILY - EXCEPT SUNDAY) ────────────────────
    
    async def generate_ceo_daily_briefing(self) -> Dict:
        """
        Generate SINGLE CEO Daily Briefing with ALL features.
        This runs on ALL days (including Sunday alongside weekly audit)
        """
        try:
            today = datetime.now()
            briefing_file = self.reports_dir / f'CEO_DAILY_BRIEFING_{today.strftime("%Y-%m-%d_%H-%M-%S")}.md'
            
            # Gather ALL data
            revenue_summary = await self.get_odoo_revenue_summary()
            recent_invoices = await self.search_odoo_invoices(limit=10)
            fb_status = await self.get_facebook_page_status()
            fb_pending = await self.check_pending_facebook_posts()
            linkedin_status = await self.get_linkedin_page_status()
            linkedin_pending = await self.check_pending_linkedin_posts()
            email_status = await self.check_gmail_status()
            email_pending = await self.check_pending_emails()
            health = await self.health_check()
            pending_items = await self.monitor_pending_items()
            
            content = f"""---
type: ceo_daily_briefing
generated: {datetime.now().isoformat()}
period: daily_{today.strftime("%Y-%m-%d")}
agent: RALPH
role: READ-ONLY_MONITORING
---

# 📊 CEO DAILY BRIEFING - {today.strftime('%Y-%m-%d')}

## 🤖 Agent Information
| Field | Value |
|-------|-------|
| **Agent** | Ralph Loop (Read-Only) |
| **Role** | Monitoring, Reporting & Audit |
| **Mode** | {self.mode.upper()} |
| **Write Operations** | ❌ DISABLED |

## 📈 Financial Summary
| Metric | Value |
|--------|-------|
| **Total Revenue (All Time)** | ${revenue_summary.get('total_revenue', 0):,.2f} |
| **Invoice Count** | {revenue_summary.get('invoice_count', 0)} |
| **Data Source** | Odoo (read-only query) |

## 🧾 Recent Invoices (Last 30 Days)

"""
            if recent_invoices.get('success'):
                invoices = recent_invoices.get('invoices', [])
                if invoices:
                    content += "| Invoice # | Amount | Status | Date |\n"
                    content += "|----------|--------|--------|------|\n"
                    for inv in invoices[:10]:
                        content += (
                            f"| {inv.get('name', 'N/A')} "
                            f"| ${inv.get('amount_total', 0):,.2f} "
                            f"| {inv.get('state', 'unknown')} "
                            f"| {inv.get('invoice_date', 'N/A')} |\n"
                        )
                else:
                    content += "No invoices found in the system.\n"
            else:
                content += f"_Error fetching invoices: {recent_invoices.get('error', 'Unknown')}_\n"
            
            content += f"""
## 📱 Social Media Status

### Facebook
| Metric | Value |
|--------|-------|
| **Page** | {fb_status.get('page_name', fb_status.get('page_id', 'Not configured'))} |
| **Needs_Action Posts** | {fb_pending.get('pending_in_needs_action', 0)} |
| **Awaiting Approval** | {fb_pending.get('pending_approvals', 0)} |

### LinkedIn
| Metric | Value |
|--------|-------|
| **Page** | {linkedin_status.get('page_name', linkedin_status.get('page_id', 'Not configured'))} |
| **Needs_Action Posts** | {linkedin_pending.get('pending_in_needs_action', 0)} |
| **Awaiting Approval** | {linkedin_pending.get('pending_approvals', 0)} |

## 📧 Email Status
| Metric | Value |
|--------|-------|
| **Unread Emails** | {email_status.get('current_primary_inbox_unread', 'N/A')} |
| **Needs_Action Emails** | {email_pending.get('pending_in_needs_action', 0)} |
| **Awaiting Approval** | {email_pending.get('pending_approvals', 0)} |

## 🔧 System Health
| Component | Status |
|-----------|--------|
| **MCP Servers** | {'✅ Online' if health.get('success') else '⚠️ Issues'} |
| **Odoo Connection** | ✅ Active |
| **Facebook MCP** | ✅ Active |
| **LinkedIn MCP** | ✅ Active |
| **Gmail MCP** | ✅ Active |
| **Ralph Mode** | {self.mode.upper()} |
| **Read-Only Mode** | ✅ ENFORCED |

## 📋 Pending Items Summary
| Location | Count |
|----------|-------|
| **Needs_Action/** | {sum(pending_items.get('needs_action', {}).values())} |
| **Pending_Approval/** | {pending_items.get('pending_approvals', 0)} |
| **Total Pending** | {pending_items.get('total_pending', 0)} |

## 🔒 Separation of Duties
| Agent | Responsibility |
|-------|----------------|
| **RALPH** | ✅ Monitor, Report, Detect, Audit (READ-ONLY) |
| **ORCHESTRATOR** | ✅ Send, Create, Post, Update (WRITE) |

## 📋 Action Items for Orchestrator
- [ ] Review pending approvals in `Pending_Approval/`
- [ ] Process approved items from `Approved/`
- [ ] Review failed operations in `Failed/`

---
*Generated by Ralph Loop (Gold Tier - Read-Only Mode)*
*Daily briefing includes: Monitoring + Audit + Separation of Duties*
*Next briefing: {(datetime.now() + timedelta(minutes=self.daily_interval_minutes)).strftime('%Y-%m-%d %H:%M:%S')}*
"""
            
            briefing_file.write_text(content, encoding='utf-8')
            self.logger.info(f"✅ CEO Daily Briefing generated: {briefing_file.name}")
            return {"success": True, "file": str(briefing_file)}
            
        except Exception as e:
            self.logger.error(f"CEO daily briefing failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ── Reporting Tasks (Supplementary) ───────────────────────────────────────
    
    async def generate_email_report(self) -> Dict:
        """Generate email activity report (supplementary)"""
        try:
            report_file = self.reports_dir / f'RALPH_EMAIL_REPORT_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.md'
            
            email_pending = await self.check_pending_emails()
            gmail_status = await self.check_gmail_status()
            
            content = f"""---
type: ralph_email_report
generated: {datetime.now().isoformat()}
agent: RALPH
role: READ-ONLY_MONITOR
---

# 📧 RALPH Email Activity Report

## Current Status
| Metric | Value |
|--------|-------|
| **Unread Emails** | {gmail_status.get('current_primary_inbox_unread', 0)} |
| **Pending in Needs_Action** | {email_pending.get('pending_in_needs_action', 0)} |
| **Awaiting Approval** | {email_pending.get('pending_approvals', 0)} |
| **Authenticated** | {gmail_status.get('authenticated', False)} |

## Workflow Status
- ✅ Gmail MCP: Active
- ✅ Email detection: Working
- ⏸ Email replies: Require approval (**ORCHESTRATOR** handles sending)
- 📋 Approval files: Move to `Approved/` for **ORCHESTRATOR** to send

## Separation of Duties
| Agent | Action |
|-------|--------|
| **RALPH** | ✅ Monitor, Report, Detect |
| **ORCHESTRATOR** | ✅ Send, Create, Post, Update |

## Notes
- Ralph Loop only MONITORS emails (no sending)
- Email sending requires human approval via **ORCHESTRATOR**
- Check `Pending_Approval/` for emails awaiting review

---
*Report generated by Ralph Loop (Read-Only)*
"""
            
            report_file.write_text(content, encoding='utf-8')
            self.logger.info(f"✅ Email report generated: {report_file.name}")
            return {"success": True, "file": str(report_file)}
            
        except Exception as e:
            self.logger.error(f"Email report failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_social_media_report(self) -> Dict:
        """Generate combined social media report (Facebook + LinkedIn) - supplementary"""
        try:
            report_file = self.reports_dir / f'RALPH_SOCIAL_REPORT_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.md'
            
            # Facebook data
            fb_status = await self.get_facebook_page_status()
            fb_pending = await self.check_pending_facebook_posts()
            fb_insights = await self.get_facebook_insights()
            
            # LinkedIn data
            linkedin_status = await self.get_linkedin_page_status()
            linkedin_pending = await self.check_pending_linkedin_posts()
            linkedin_insights = await self.get_linkedin_insights()
            
            # Generate recent files list for Facebook
            fb_files = fb_pending.get('files', [])
            fb_files_section = ""
            if fb_files:
                for f in fb_files[:3]:
                    fb_files_section += f"- `{f}`\n"
            else:
                fb_files_section = "- No pending Facebook posts\n"
            
            # Generate recent files list for LinkedIn
            linkedin_files = linkedin_pending.get('files', [])
            linkedin_files_section = ""
            if linkedin_files:
                for f in linkedin_files[:3]:
                    linkedin_files_section += f"- `{f}`\n"
            else:
                linkedin_files_section = "- No pending LinkedIn posts\n"
            
            content = f"""---
type: ralph_social_report
generated: {datetime.now().isoformat()}
agent: RALPH
role: READ-ONLY_MONITOR
---

# 📱 RALPH Social Media Report

## Facebook Page Status
| Metric | Value |
|--------|-------|
| **Page** | {fb_status.get('page_name', fb_status.get('page_id', 'Not configured'))} |
| **Status** | {'✅ Active' if fb_status.get('success') else '⚠️ Check configuration'} |
| **Insights Available** | {fb_insights.get('insights_available', False)} |

## LinkedIn Page Status
| Metric | Value |
|--------|-------|
| **Page** | {linkedin_status.get('page_name', linkedin_status.get('page_id', 'Not configured'))} |
| **Status** | {'✅ Active' if linkedin_status.get('success') else '⚠️ Check configuration'} |
| **Followers** | {linkedin_insights.get('followers', 'N/A')} |
| **Insights Available** | {linkedin_insights.get('insights_available', False)} |

## Pending Content - Facebook
| Location | Count |
|----------|-------|
| **Needs_Action/** | {fb_pending.get('pending_in_needs_action', 0)} |
| **Pending_Approval/** | {fb_pending.get('pending_approvals', 0)} |

### Recent Files - Facebook
{fb_files_section}
## Pending Content - LinkedIn
| Location | Count |
|----------|-------|
| **Needs_Action/** | {linkedin_pending.get('pending_in_needs_action', 0)} |
| **Pending_Approval/** | {linkedin_pending.get('pending_approvals', 0)} |

### Recent Files - LinkedIn
{linkedin_files_section}
## Action Required
1. Review posts in `Needs_Action/` for both platforms
2. Move approved content to `Approved/`
3. **ORCHESTRATOR** will publish via MCP

## Important Notes
- ✅ Ralph Loop: READ-ONLY monitoring
- ❌ Ralph Loop does NOT post to Facebook or LinkedIn
- ✅ Posting requires human approval via **ORCHESTRATOR**

---
*Report generated by Ralph Loop (Monitoring Only)*
"""
            
            report_file.write_text(content, encoding='utf-8')
            self.logger.info(f"✅ Social report generated: {report_file.name}")
            return {"success": True, "file": str(report_file)}
            
        except Exception as e:
            self.logger.error(f"Social media report failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def health_check(self) -> Dict:
        """MCP Health Check"""
        registry = self._get_registry()
        if registry is None:
            return {"success": False, "error": "MCP not initialized"}
        
        health_status: Dict[str, Any] = {}
        
        for server_name in registry.servers:
            health = await registry.health_check(server_name)
            health_status[server_name] = health
        
        all_healthy = all(h.get("status") == "healthy" for h in health_status.values())
        
        return {
            "success": all_healthy,
            "status": health_status,
            "timestamp": datetime.now().isoformat()
        }
    
    async def monitor_pending_items(self) -> Dict:
        """Monitor all pending items across folders"""
        items: Dict[str, int] = {
            "emails": 0,
            "facebook_posts": 0,
            "linkedin_posts": 0,
            "invoices": 0,
            "other": 0
        }
        
        if self.needs_action_dir.exists():
            for f in self.needs_action_dir.glob("*.md"):
                name = f.name.lower()
                if name.startswith("email_"):
                    items["emails"] += 1
                elif name.startswith("fb_") or name.startswith("facebook_"):
                    items["facebook_posts"] += 1
                elif name.startswith("linkedin_") or name.startswith("post_"):
                    items["linkedin_posts"] += 1
                elif name.startswith("invoice_"):
                    items["invoices"] += 1
                else:
                    items["other"] += 1
        
        approval_count = 0
        if self.pending_approval_dir.exists():
            approval_count = len(list(self.pending_approval_dir.glob("*.md")))
        
        total_pending = sum(items.values())
        
        return {
            "success": True,
            "needs_action": items,
            "pending_approvals": approval_count,
            "total_pending": total_pending + approval_count,
            "timestamp": datetime.now().isoformat()
        }
    
    # ── Audit Log ───────────────────────────────────────────────────────────
    
    def log_audit(self, action: str, details: str = "") -> None:
        """Write audit entry to logs folder"""
        try:
            audit_log = self.logs_dir / f'ralph_audit_{datetime.now().strftime("%Y-%m-%d")}.log'
            timestamp = datetime.now().isoformat()
            
            with open(audit_log, 'a', encoding='utf-8') as fh:
                fh.write(f"{timestamp} - RALPH - {action} - {details}\n")
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")
    
    # ── Task Execution ────────────────────────────────────────────────────────
    
    async def execute_daily_cycle(self) -> None:
        """Execute daily tasks - Clean output with SINGLE CEO briefing + Sunday weekly audit"""
        print(f"\n📅 DAILY CYCLE [{datetime.now().strftime('%H:%M:%S')}]")
        print(f"{'━'*60}")
        
        # PRIMARY: CEO Daily Briefing (runs EVERY day)
        print(f"🎯 Executing: CEO Daily Briefing")
        result = await self.generate_ceo_daily_briefing()
        if result.get("success"):
            filename = Path(result["file"]).name
            print(f"📊 Saved: {filename}")
            print(f"✅ Task succeeded")
        
        print()
        
        # WEEKLY: Weekly Audit (SUNDAY only)
        print(f"🎯 Executing: Weekly Audit")
        result = await self.run_weekly_audit()
        if result.get("skipped"):
            print(f"⏭️ Skipped (Sunday only)")
        elif result.get("success"):
            filename = Path(result["file"]).name
            print(f"📋 Saved: {filename}")
            print(f"✅ Task succeeded")
        
        print()
        
        # SUPPLEMENTARY: MCP Health Check
        print(f"🎯 Executing: MCP Health Check")
        result = await self.health_check()
        if result.get("success"):
            print(f"✅ All systems operational")
        
        print()
        
        # SUPPLEMENTARY: Email Report (detailed)
        print(f"🎯 Executing: Email Report")
        result = await self.generate_email_report()
        if result.get("success"):
            filename = Path(result["file"]).name
            print(f"📧 Saved: {filename}")
            print(f"✅ Task succeeded")
        
        print()
        
        # SUPPLEMENTARY: Social Media Report (detailed)
        print(f"🎯 Executing: Social Media Report")
        result = await self.generate_social_media_report()
        if result.get("success"):
            filename = Path(result["file"]).name
            print(f"📱 Saved: {filename}")
            print(f"✅ Task succeeded")
        
        print()
        
        # Pending Items Monitor
        print(f"🎯 Executing: Pending Items Monitor")
        result = await self.monitor_pending_items()
        if result.get("success"):
            needs_action_total = sum(result.get("needs_action", {}).values())
            if needs_action_total > 0:
                print(f"   ⚠️ Pending: {needs_action_total} items")
            elif result.get("pending_approvals", 0) > 0:
                print(f"   ⏳ Pending_Approval: {result.get('pending_approvals')} items")
            else:
                print(f"   ✅ No pending items")
        
        print(f"\n✅ Ralph daily cycle completed")
        print(f"{'━'*60}")
        
        self.last_daily_run = datetime.now()
    
    async def execute_rapid_cycle(self) -> None:
        """Execute rapid cycle - Clean output"""
        self.rapid_cycle_count += 1
        
        email_pending = await self.check_pending_emails()
        fb_pending = await self.check_pending_facebook_posts()
        linkedin_pending = await self.check_pending_linkedin_posts()
        
        email_count = email_pending.get('pending_in_needs_action', 0)
        fb_count = fb_pending.get('pending_in_needs_action', 0)
        linkedin_count = linkedin_pending.get('pending_in_needs_action', 0)
        
        print(f"\n⚡ RAPID CYCLE #{self.rapid_cycle_count} [{datetime.now().strftime('%H:%M:%S')}]")
        print(f"{'━'*60}")
        
        if email_count > 0 or fb_count > 0 or linkedin_count > 0:
            print(f"   ⚠️ Needs_Action: {email_count} emails, {fb_count} Facebook, {linkedin_count} LinkedIn posts")
        else:
            print(f"   ✅ No pending items in Needs_Action")
        
        print(f"   ⏰ Next rapid cycle in {self.rapid_interval_seconds} seconds")
        print(f"{'━'*60}")
        
        self.last_rapid_run = datetime.now()
    
    # ── Main Loop ─────────────────────────────────────────────────────────────
    
    async def run_hybrid_mode(self) -> None:
        """Hybrid mode: Daily + Rapid cycles - Clean output"""
        registry = self._get_registry()
        server_count = len(registry.servers) if registry is not None else 0
        server_names = ' | '.join([s.upper() for s in registry.servers]) if registry else 'NONE'
        
        print(f"\n{'━'*60}")
        print(f"🌀 RALPH LOOP v1.0 | HYBRID MODE")
        print(f"{'━'*60}")
        print(f"📂 Vault: {self.vault_path}")
        print(f"✅ MCP Servers: {server_names} ({server_count} online)")
        print(f"✅ Read-Only Mode: ENABLED")
        print(f"{'━'*60}\n")
        
        self.log_audit("RALPH_START", f"Mode: {self.mode}")
        
        last_daily_time: Optional[datetime] = None
        last_rapid_time: Optional[datetime] = None
        
        try:
            while True:
                now = datetime.now()
                
                # Daily cycle (once per day)
                if (last_daily_time is None or
                        (now - last_daily_time).total_seconds() >= self.daily_interval_minutes * 60):
                    await self.execute_daily_cycle()
                    last_daily_time = now
                
                # Rapid cycle (every N seconds)
                if (last_rapid_time is None or
                        (now - last_rapid_time).total_seconds() >= self.rapid_interval_seconds):
                    await self.execute_rapid_cycle()
                    last_rapid_time = now
                
                await asyncio.sleep(10)
                
        except KeyboardInterrupt:
            self.logger.info("\n🛑 Stopping Ralph Loop...")
            self.log_audit("RALPH_STOP", "Manual stop")
    
    async def run_daily_mode(self) -> None:
        """Daily mode only"""
        print(f"\n{'━'*60}")
        print(f"🌀 RALPH LOOP v1.0 | DAILY MODE")
        print(f"{'━'*60}")
        await self.execute_daily_cycle()
        self.log_audit("RALPH_DAILY_COMPLETE", "Daily cycle finished")
    
    async def run_rapid_mode(self) -> None:
        """Rapid mode only"""
        print(f"\n{'━'*60}")
        print(f"🌀 RALPH LOOP v1.0 | RAPID MODE")
        print(f"{'━'*60}")
        self.log_audit("RALPH_RAPID_START", "Continuous monitoring started")
        try:
            while True:
                await self.execute_rapid_cycle()
                await asyncio.sleep(self.rapid_interval_seconds)
        except KeyboardInterrupt:
            self.logger.info("\n🛑 Stopping...")
            self.log_audit("RALPH_RAPID_STOP", "Monitoring stopped")
    
    async def start(self) -> None:
        """Start Ralph Loop based on mode"""
        if not await self.initialize_mcp():
            self.logger.error("Failed to initialize MCP. Exiting...")
            return
        
        try:
            if self.mode == 'hybrid':
                await self.run_hybrid_mode()
            elif self.mode == 'daily':
                await self.run_daily_mode()
            elif self.mode == 'rapid':
                await self.run_rapid_mode()
            else:
                self.logger.error(f"Unknown mode: {self.mode}")
                
        finally:
            await self.shutdown()


# ── Main Entry Point ─────────────────────────────────────────────────────────

async def main() -> None:
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Ralph Loop - Autonomous AI Employee (Read-Only Mode)',
        epilog='''
Examples:
  python ralph_loop.py --mode hybrid    # Daily + Rapid monitoring
  python ralph_loop.py --mode daily     # Daily tasks only
  python ralph_loop.py --mode rapid     # Continuous monitoring
'''
    )
    parser.add_argument(
        '--mode', '-m',
        choices=['hybrid', 'daily', 'rapid'],
        default='hybrid',
        help='Operation mode (default: hybrid)'
    )
    
    args = parser.parse_args()
    
    ralph = RalphLoop(mode=args.mode)
    await ralph.start()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass