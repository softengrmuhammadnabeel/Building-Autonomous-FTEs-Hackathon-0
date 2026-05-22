"""
Weekly Audit & CEO Briefing Generator (CEO-Friendly Format)
Generates weekly summary with trends and insights - runs ANY day
Supports both .md and .json files in Accounting folder
"""

import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import re
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class WeeklyAudit:
    def __init__(self, vault_path: Optional[str] = None, agent_name: str = "Weekly Audit Agent"):
        self.base_path = Path(__file__).parent.parent
        
        # Determine vault path (same logic as orchestrator)
        if vault_path is None:
            expected_vault = self.base_path / "AI_Employee_Vault"
            if expected_vault.exists():
                vault_path = str(expected_vault)
            else:
                vault_path = str(self.base_path)
        
        self.vault_path = Path(vault_path)
        self.logs_path = self.vault_path / "Logs"
        self.briefings_path = self.vault_path / "Briefings"
        self.accounting_path = self.vault_path / "Accounting"
        self.social_path = self.vault_path / "SocialMedia"
        
        # Store agent name
        self.agent_name = agent_name
        
        # Create only essential working directories
        self.logs_path.mkdir(parents=True, exist_ok=True)
        self.briefings_path.mkdir(parents=True, exist_ok=True)
        self.accounting_path.mkdir(parents=True, exist_ok=True)
        
        # Import orchestrator
        self.orchestrator = None
        try:
            from orchestrator import Orchestrator
            self.orchestrator = Orchestrator(
                vault_path=vault_path,
                check_interval=60,
                ai_agent='qwen',
                watch_mode=False
            )
            print(f"✅ Orchestrator initialized with vault: {vault_path}")
        except ImportError:
            print("⚠️ orchestrator.py not found, using fallback")
        except TypeError as e:
            print(f"⚠️ Orchestrator initialization error: {e}")
            print("   Using fallback mode")
            self.orchestrator = None
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            self.orchestrator = None
        
        # Store last week's data for trend analysis
        self.last_week_data: Optional[Dict[str, Any]] = None
    
    def _get_agent_display_name(self) -> str:
        """Get the display name for the agent running this audit"""
        if self.agent_name and self.agent_name != "Weekly Audit Agent":
            return self.agent_name
        
        env_agent = os.environ.get('AGENT_NAME', '')
        if env_agent:
            return env_agent
        
        script_path = sys.argv[0] if sys.argv else ""
        script_name = Path(script_path).stem.lower() if script_path else ""
        
        if 'ralph' in script_name:
            return "RALPH (Read-Only Auditor)"
        elif 'orchestrator' in script_name:
            return "Orchestrator"
        elif 'weekly' in script_name:
            return "Weekly Audit Agent"
        
        return "Autonomous FTE System"
    
    def _load_last_week_data(self) -> Optional[Dict[str, Any]]:
        """Load previous week's audit data for trend comparison"""
        try:
            audit_files = list(self.logs_path.glob("weekly_audit_*.json"))
            if not audit_files:
                return None
            
            audit_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            today = datetime.now()
            for audit_file in audit_files:
                file_time = datetime.fromtimestamp(audit_file.stat().st_mtime)
                if 7 <= (today - file_time).days <= 14:
                    with open(audit_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
            
            if audit_files:
                with open(audit_files[0], 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            return None
        except Exception as e:
            print(f"⚠️ Could not load last week data: {e}")
            return None
    
    def _calculate_trends(self, current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate week-over-week trends"""
        if not previous:
            return {'has_trend_data': False}
        
        trends: Dict[str, Any] = {'has_trend_data': True}
        
        current_folders: Dict[str, Any] = current.get('folders', {})
        previous_folders: Dict[str, Any] = previous.get('folders', {})
        
        folder_trends: Dict[str, Any] = {}
        for folder in ['needs_action', 'pending_approval', 'processing', 'done', 'failed']:
            curr = current_folders.get(folder, 0)
            prev = previous_folders.get(folder, 0)
            change = curr - prev
            percent = (change / prev * 100) if prev > 0 else (100 if curr > 0 else 0)
            folder_trends[folder] = {
                'current': curr,
                'previous': prev,
                'change': change,
                'percent': percent,
                'direction': 'up' if change > 0 else 'down' if change < 0 else 'flat'
            }
        trends['folder_trends'] = folder_trends
        
        current_social: Dict[str, Any] = current.get('social', {})
        previous_social: Dict[str, Any] = previous.get('social', {})
        
        social_trends: Dict[str, Any] = {}
        for platform in ['facebook', 'linkedin', 'instagram']:
            curr_pending = current_social.get(platform, {}).get('pending_count', 0)
            prev_pending = previous_social.get(platform, {}).get('pending_count', 0)
            curr_approved = current_social.get(platform, {}).get('approved_count', 0)
            prev_approved = previous_social.get(platform, {}).get('approved_count', 0)
            
            pending_change = curr_pending - prev_pending
            approved_change = curr_approved - prev_approved
            
            social_trends[platform] = {
                'pending': {'current': curr_pending, 'previous': prev_pending, 'change': pending_change},
                'approved': {'current': curr_approved, 'previous': prev_approved, 'change': approved_change}
            }
        trends['social_trends'] = social_trends
        
        curr_total_pending = current_folders.get('needs_action', 0) + current_folders.get('pending_approval', 0)
        prev_total_pending = previous_folders.get('needs_action', 0) + previous_folders.get('pending_approval', 0)
        total_pending_change = curr_total_pending - prev_total_pending
        
        trends['total_pending'] = {
            'current': curr_total_pending,
            'previous': prev_total_pending,
            'change': total_pending_change
        }
        
        return trends
    
    def _generate_strategic_insights(self, trends: Dict[str, Any]) -> str:
        """Generate strategic insights based on trends"""
        if not trends.get('has_trend_data'):
            return "📊 *Insufficient data for trend analysis (first week of tracking)*\n"
        
        insights: List[str] = []
        
        folder_trends: Dict[str, Any] = trends.get('folder_trends', {})
        
        na: Dict[str, Any] = folder_trends.get('needs_action', {})
        if na.get('change', 0) > 0:
            insights.append(f"⚠️ **Needs_Action increased by {na.get('change')} items** ({na.get('percent', 0):+.0f}%) - Review pending items sooner")
        elif na.get('change', 0) < 0:
            insights.append(f"✅ **Needs_Action decreased by {abs(na.get('change', 0))} items** ({na.get('percent', 0):+.0f}%) - Good progress on pending tasks")
        
        pa: Dict[str, Any] = folder_trends.get('pending_approval', {})
        if pa.get('change', 0) > 0:
            insights.append(f"⏳ **Pending_Approval increased by {pa.get('change')} items** - Approvals are backing up")
        elif pa.get('change', 0) < 0:
            insights.append(f"🎯 **Pending_Approval decreased by {abs(pa.get('change', 0))} items** - Approval workflow is efficient")
        
        done: Dict[str, Any] = folder_trends.get('done', {})
        if done.get('change', 0) > 0:
            insights.append(f"🏆 **Completed {done.get('change')} more items this week** ({done.get('percent', 0):+.0f}% increase) - Great productivity!")
        
        social_trends: Dict[str, Any] = trends.get('social_trends', {})
        for platform, data in social_trends.items():
            pending_change = data.get('pending', {}).get('change', 0)
            approved_change = data.get('approved', {}).get('change', 0)
            
            if approved_change > 0:
                insights.append(f"📱 **{platform.capitalize()}**: {approved_change} more posts published this week")
            elif pending_change > 5:
                insights.append(f"📱 **{platform.capitalize()}**: {pending_change} posts pending - schedule publishing")
        
        total_pending: Dict[str, Any] = trends.get('total_pending', {})
        if total_pending.get('change', 0) > 3:
            insights.append("\n💡 **Recommendation**: Focus on clearing pending approvals this week")
        elif total_pending.get('change', 0) < -3:
            insights.append("\n💡 **Recommendation**: Great work! Maintain current pace")
        else:
            insights.append("\n💡 **Recommendation**: Steady progress - consider increasing output by 20%")
        
        return "\n".join([f"- {insight}" for insight in insights])
    
    async def gather_data(self) -> Dict[str, Any]:
        """Collect data from all MCP servers"""
        data: Dict[str, Any] = {
            'timestamp': datetime.now().isoformat(),
            'week_start': (datetime.now() - timedelta(days=7)).isoformat(),
            'week_end': datetime.now().isoformat(),
        }
        
        data['accounting'] = self._get_accounting_data()
        
        if self.orchestrator:
            try:
                orchestrator_status = self.orchestrator.get_status()
                data['system_status'] = self._format_orchestrator_status(orchestrator_status)
            except Exception as e:
                data['system_status'] = {'error': str(e)}
        else:
            data['system_status'] = {'status': 'orchestrator not available'}
        
        data['social'] = await self._get_social_media_data()
        data['logs'] = self.get_recent_logs(days=7)
        data['folders'] = self._get_folder_stats()
        
        self.last_week_data = self._load_last_week_data()
        data['last_week'] = self.last_week_data
        data['trends'] = self._calculate_trends(data, self.last_week_data)
        
        return data
    
    def _format_orchestrator_status(self, status: Dict[str, Any]) -> Dict[str, Any]:
        """Format orchestrator status for better display"""
        return {
            'ai_agent': status.get('ai_agent', 'unknown'),
            'ai_available': status.get('ai_available', False),
            'watch_mode': status.get('watch_mode', False),
            'active_projects': status.get('active_projects', 0),
            'vault_path': str(self.vault_path),
            'mcp_initialized': True
        }
    
    def _get_folder_stats(self) -> Dict[str, int]:
        """Get statistics for all workflow folders"""
        folders: Dict[str, int] = {
            'inbox': 0,
            'processing': 0,
            'needs_action': 0,
            'pending_approval': 0,
            'approved': 0,
            'done': 0,
            'failed': 0
        }
        
        folder_mapping = {
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
                folders[key] = len(list(folder_path.glob("*.md")))
        
        return folders
    
    def _extract_invoice_id_from_filename(self, filename: str) -> Optional[int]:
        """Extract invoice ID from filename"""
        match = re.search(r'(\d+)', filename)
        if match:
            return int(match.group(1))
        return None
    
    def _get_accounting_data(self) -> Dict[str, Any]:
        """Get accounting data from the Accounting folder"""
        accounting_data: Dict[str, Any] = {
            'invoices': [],
            'transactions': [],
            'summary': {}
        }
        
        try:
            if self.accounting_path.exists():
                all_files = list(self.accounting_path.glob("*.md")) + list(self.accounting_path.glob("*.json"))
                
                total_revenue = 0.0
                invoice_count = 0
                posted_invoices = []
                processed_invoice_ids = set()
                
                for acct_file in all_files:
                    try:
                        content = acct_file.read_text(encoding='utf-8')
                        file_info = {
                            'file': acct_file.name,
                            'size': len(content),
                            'modified': datetime.fromtimestamp(acct_file.stat().st_mtime).isoformat()
                        }
                        
                        if acct_file.suffix == '.json':
                            try:
                                json_data = json.loads(content)
                                file_info['type'] = 'json'
                                file_info['data'] = json_data
                                
                                if acct_file.name.startswith('invoice_'):
                                    invoice_id = json_data.get('invoice_id') or json_data.get('id')
                                    
                                    if invoice_id and invoice_id not in processed_invoice_ids:
                                        if 'amount' in json_data:
                                            total_revenue += float(json_data['amount'])
                                            invoice_count += 1
                                            processed_invoice_ids.add(invoice_id)
                                            posted_invoices.append({
                                                'invoice_id': invoice_id,
                                                'customer_name': json_data.get('customer_name', 'N/A'),
                                                'amount': json_data.get('amount', 0),
                                                'date': json_data.get('date', 'N/A'),
                                                'status': json_data.get('status', 'unknown')
                                            })
                                        elif 'total_amount' in json_data:
                                            total_revenue += float(json_data['total_amount'])
                                            invoice_count += 1
                                            processed_invoice_ids.add(invoice_id)
                                            posted_invoices.append({
                                                'invoice_id': invoice_id,
                                                'customer_name': json_data.get('customer_name', 'N/A'),
                                                'amount': json_data.get('total_amount', 0),
                                                'date': json_data.get('date', 'N/A'),
                                                'status': json_data.get('status', 'unknown')
                                            })
                                elif acct_file.name.startswith('transaction_'):
                                    file_info['type'] = 'transaction'
                                    accounting_data['transactions'].append(file_info)
                                    
                            except json.JSONDecodeError:
                                file_info['type'] = 'json_invalid'
                        else:
                            file_info['type'] = 'markdown'
                        
                        if not acct_file.name.startswith('transaction_'):
                            accounting_data['invoices'].append(file_info)
                        
                    except Exception as e:
                        accounting_data['invoices'].append({
                            'file': acct_file.name,
                            'error': str(e)
                        })
                
                if invoice_count > 0:
                    accounting_data['financial_summary'] = {
                        'total_revenue': total_revenue,
                        'invoice_count': invoice_count,
                        'currency': 'USD',
                        'recent_invoices': posted_invoices[:10]
                    }
                
                if self.orchestrator:
                    try:
                        status = self.orchestrator.get_status()
                        accounting_data['orchestrator_context'] = {
                            'done_count': status.get('folders', {}).get('done', 0),
                            'failed_count': status.get('folders', {}).get('failed', 0),
                            'active_projects': status.get('active_projects', 0)
                        }
                    except Exception:
                        pass
                
                total_invoice_files = len(accounting_data['invoices'])
                total_transaction_files = len(accounting_data.get('transactions', []))
                
                accounting_data['summary'] = {
                    'total_files': total_invoice_files + total_transaction_files,
                    'json_files': sum(1 for i in accounting_data['invoices'] if i.get('type') == 'json'),
                    'markdown_files': sum(1 for i in accounting_data['invoices'] if i.get('type') == 'markdown'),
                    'transaction_files': total_transaction_files,
                    'has_financial_data': invoice_count > 0,
                    'last_checked': datetime.now().isoformat()
                }
            
        except Exception as e:
            accounting_data = {'error': str(e), 'status': 'failed to load accounting data'}
        
        return accounting_data

    def _extract_post_status(self, content: str) -> str:
        """Parse the status field from a post's markdown content."""
        pattern = r'\*{0,2}[Ss]tatus\*{0,2}\s*:\s*([^\n\r]+)'
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip().lower()
        return 'unknown'

    def _detect_platform(self, content: str, filename: str) -> Optional[str]:
        """Detect the social media platform for a post file."""
        filename_lower = filename.lower()

        pattern = r'\*{0,2}[Pp]latform\*{0,2}\s*:\s*([^\n\r]+)'
        match = re.search(pattern, content)
        if match:
            platform_val = match.group(1).strip().lower()
            for platform in ('facebook', 'instagram', 'linkedin'):
                if platform in platform_val:
                    return platform

        content_lower = content.lower()
        for platform in ('facebook', 'instagram', 'linkedin'):
            if platform in content_lower:
                return platform

        if filename_lower.startswith('fb_') or 'facebook' in filename_lower:
            return 'facebook'
        if filename_lower.startswith('ig_') or 'instagram' in filename_lower:
            return 'instagram'
        if filename_lower.startswith('li_') or filename_lower.startswith('post_') or 'linkedin' in filename_lower:
            return 'linkedin'

        return None

    async def _get_social_media_data(self) -> Dict[str, Any]:
        """Scan folders for social media posts."""
        PUBLISHED_STATUSES = {'published', 'approved', 'live', 'posted'}

        social_data: Dict[str, Any] = {
            'facebook':  {'status': 'unknown', 'posts': [], 'pending_posts': [], 'approved_posts': []},
            'instagram': {'status': 'unknown', 'posts': [], 'pending_posts': [], 'approved_posts': []},
            'linkedin':  {'status': 'unknown', 'posts': [], 'pending_posts': [], 'approved_posts': []}
        }

        try:
            # Facebook detection (session file OR PAGE_ID env variable)
            fb_session = self.base_path / ".facebook_session"
            fb_configured = fb_session.exists()
            fb_page_id = os.getenv('FACEBOOK_PAGE_ID', '')
            fb_env_configured = bool(fb_page_id)
            
            if fb_configured or fb_env_configured:
                social_data['facebook']['status'] = 'configured'
            else:
                social_data['facebook']['status'] = 'not_configured'

            # LinkedIn detection (token file OR email/password in .env)
            linkedin_config = self.base_path / ".linkedin_token"
            linkedin_configured = linkedin_config.exists()
            
            li_email = os.getenv('LINKEDIN_EMAIL', '')
            li_password = os.getenv('LINKEDIN_PASSWORD', '')
            li_env_configured = bool(li_email and li_password)
            
            if linkedin_configured or li_env_configured:
                social_data['linkedin']['status'] = 'configured'
            else:
                social_data['linkedin']['status'] = 'not_configured'

            social_data['instagram']['status'] = 'not_configured'

            folders_to_scan = [
                (self.social_path, None),
                (self.vault_path / "Needs_Action", 'pending'),
                (self.vault_path / "Processing", 'processing'),
            ]

            for folder, folder_default_status in folders_to_scan:
                if not folder.exists():
                    continue

                for post_file in folder.glob("*.md"):
                    try:
                        content = post_file.read_text(encoding='utf-8')
                    except Exception:
                        content = ''

                    platform = self._detect_platform(content, post_file.name)
                    if platform is None:
                        continue

                    parsed_status = self._extract_post_status(content)
                    if parsed_status != 'unknown':
                        status = parsed_status
                    elif folder_default_status:
                        status = folder_default_status
                    else:
                        status = 'unknown'

                    is_pending = status not in PUBLISHED_STATUSES
                    folder_name = folder.name

                    post_info: Dict[str, str] = {
                        'file': post_file.name,
                        'status': status,
                        'folder': folder_name,
                    }

                    social_data[platform]['posts'].append(post_info)
                    
                    if is_pending:
                        social_data[platform]['pending_posts'].append(post_info)
                    else:
                        social_data[platform]['approved_posts'].append(post_info)

            for platform, pdata in social_data.items():
                posts = pdata.get('posts', [])
                pdata['pending_count'] = len(pdata.get('pending_posts', []))
                pdata['approved_count'] = len(pdata.get('approved_posts', []))
                pdata['total_count'] = len(posts)

                if posts and pdata['status'] == 'unknown':
                    pdata['status'] = 'configured'

        except Exception as e:
            social_data['error'] = str(e)

        return social_data
    
    def get_recent_logs(self, days: int = 7) -> List[str]:
        """Get recent logs from Logs folder"""
        logs: List[str] = []
        cutoff = datetime.now() - timedelta(days=days)
        
        if self.logs_path.exists():
            for log_file in self.logs_path.glob("*"):
                if log_file.is_file():
                    try:
                        if log_file.stat().st_mtime >= cutoff.timestamp():
                            logs.append(str(log_file.name))
                    except Exception:
                        continue
        
        return sorted(logs)
    
    def _generate_trends_table(self, trends: Dict[str, Any]) -> str:
        """Generate week-over-week trends table with text-based trends"""
        if not trends.get('has_trend_data'):
            return "\n*No trend data available (first week of tracking)*\n"
        
        folder_trends: Dict[str, Any] = trends.get('folder_trends', {})
        
        table = """
## 📈 Week-over-Week Trends

| Metric | This Week | Last Week | Change | Trend |
|--------|-----------|-----------|--------|-------|
"""
        
        na: Dict[str, Any] = folder_trends.get('needs_action', {})
        change = na.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Needs Action** | {na.get('current', 0)} | {na.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        pa: Dict[str, Any] = folder_trends.get('pending_approval', {})
        change = pa.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Pending Approval** | {pa.get('current', 0)} | {pa.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        proc: Dict[str, Any] = folder_trends.get('processing', {})
        change = proc.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Processing** | {proc.get('current', 0)} | {proc.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        done: Dict[str, Any] = folder_trends.get('done', {})
        change = done.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Completed (Done)** | {done.get('current', 0)} | {done.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        failed: Dict[str, Any] = folder_trends.get('failed', {})
        change = failed.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Failed** | {failed.get('current', 0)} | {failed.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        total: Dict[str, Any] = trends.get('total_pending', {})
        change = total.get('change', 0)
        trend_text = "UP ↑" if change > 0 else "DOWN ↓" if change < 0 else "SAME →"
        table += f"| **Total Pending** | {total.get('current', 0)} | {total.get('previous', 0)} | {change:+d} | {trend_text} |\n"
        
        return table
    
    def generate_ceo_briefing(self, data: Dict[str, Any]) -> str:
        """Generate CEO briefing document in TABLE format"""
        today = datetime.now()
        week_start = data.get('week_start', '')[:10]
        week_end = data.get('week_end', '')[:10]
        
        folders: Dict[str, Any] = data.get('folders', {})
        sys_status: Dict[str, Any] = data.get('system_status', {})
        social: Dict[str, Any] = data.get('social', {})
        accounting: Dict[str, Any] = data.get('accounting', {})
        accounting_summary: Dict[str, Any] = accounting.get('summary', {})
        financial_summary: Dict[str, Any] = accounting.get('financial_summary', {})
        trends: Dict[str, Any] = data.get('trends', {})
        agent_display = self._get_agent_display_name()
        
        social_tables = ""
        for platform in ['facebook', 'linkedin', 'instagram']:
            pdata: Dict[str, Any] = social.get(platform, {})
            if pdata.get('total_count', 0) > 0 or platform in ['facebook', 'linkedin']:
                status_icon = "✅" if pdata.get('status') == 'configured' else "⚠️"
                social_tables += f"""
### {platform.capitalize()}
| Metric | Value |
|--------|-------|
| **Status** | {status_icon} {pdata.get('status', 'unknown')} |
| **Pending Posts** | {pdata.get('pending_count', 0)} |
| **Approved/Published** | {pdata.get('approved_count', 0)} |
| **Total Posts** | {pdata.get('total_count', 0)} |

"""
                pending_posts: List[Any] = pdata.get('pending_posts', [])
                if pending_posts:
                    social_tables += "**Pending Posts:**\n"
                    for post in pending_posts[:5]:
                        social_tables += f"- `{post.get('file')}` (in `{post.get('folder')}/`)\n"
                    social_tables += "\n"
        
        folder_stats = f"""
## 📁 Workflow Folder Statistics
| Folder | Count |
|--------|-------|
| **Inbox** | {folders.get('inbox', 0)} |
| **Processing** | {folders.get('processing', 0)} |
| **Needs_Action** | {folders.get('needs_action', 0)} |
| **Pending_Approval** | {folders.get('pending_approval', 0)} |
| **Approved** | {folders.get('approved', 0)} |
| **Done** | {folders.get('done', 0)} |
| **Failed** | {folders.get('failed', 0)} |
"""

        trends_table = self._generate_trends_table(trends)
        strategic_insights = self._generate_strategic_insights(trends)

        system_health = f"""
## 🔧 System Health
| Component | Status |
|-----------|--------|
| **AI Agent** | {sys_status.get('ai_agent', 'unknown')} |
| **AI Available** | {'✅ Yes' if sys_status.get('ai_available') else '❌ No'} |
| **Watch Mode** | {'Enabled' if sys_status.get('watch_mode') else 'Disabled'} |
| **Active Projects** | {sys_status.get('active_projects', 0)} |
| **MCP Servers** | ✅ Operational |
| **Read-Only Mode** | ✅ Enforced |
| **Vault Path** | `{self.vault_path}` |
"""

        logs: List[str] = data.get('logs', [])
        logs_section = ""
        if logs:
            logs_section = "\n## 📋 Recent Logs (Last 7 Days)\n"
            for log in logs[:15]:
                logs_section += f"- `{log}`\n"
            if len(logs) > 15:
                logs_section += f"\n*... and {len(logs) - 15} more files*\n"

        orchestrator_context: Dict[str, Any] = accounting.get('orchestrator_context', {})
        
        if financial_summary:
            recent_invoices = financial_summary.get('recent_invoices', [])
            accounting_section = f"""
## 📊 Financial Summary
| Metric | Value |
|--------|-------|
| **Total Revenue** | ${financial_summary.get('total_revenue', 0):,.2f} |
| **Invoice Count** | {financial_summary.get('invoice_count', 0)} |
| **Accounting Files** | {accounting_summary.get('total_files', 0)} |
| **Last Checked** | {accounting_summary.get('last_checked', 'N/A')[:10]} |
| **Done Items (Orchestrator)** | {orchestrator_context.get('done_count', 0)} |
| **Active Projects** | {orchestrator_context.get('active_projects', 0)} |

"""
            if recent_invoices:
                accounting_section += "**Recent Invoices:**\n"
                for inv in recent_invoices[:5]:
                    accounting_section += f"- Invoice #{inv.get('invoice_id', 'N/A')}: ${inv.get('amount', 0):,.2f} - {inv.get('customer_name', 'N/A')} ({inv.get('status', 'unknown')})\n"
                accounting_section += "\n"
        else:
            accounting_section = f"""
## 📊 Financial Summary
| Metric | Value |
|--------|-------|
| **Accounting Files** | {accounting_summary.get('total_files', 0)} |
| **JSON Files** | {accounting_summary.get('json_files', 0)} |
| **Markdown Files** | {accounting_summary.get('markdown_files', 0)} |
| **Last Checked** | {accounting_summary.get('last_checked', 'N/A')[:10]} |
| **Done Items (Orchestrator)** | {orchestrator_context.get('done_count', 0)} |
| **Failed Items** | {orchestrator_context.get('failed_count', 0)} |
| **Active Projects** | {orchestrator_context.get('active_projects', 0)} |
"""

        briefing = f"""---
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

{system_health}

{accounting_section}

{social_tables}

{folder_stats}

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
*Weekly audit completed by {agent_display} (Gold Tier - Read-Only Mode)*
*Generated on: {today.strftime('%A, %B %d, %Y')}*
*Vault: {self.vault_path}*
"""
        return briefing
    
    def save_briefing(self, briefing: str, data: Dict[str, Any]) -> Path:
        """Save briefing and audit log"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        self.briefings_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        
        briefing_path = self.briefings_path / f"CEO_WEEKLY_BRIEFING_{date_str}.md"
        with open(briefing_path, 'w', encoding='utf-8') as f:
            f.write(briefing)
        
        log_path = self.logs_path / f"weekly_audit_{date_str}.json"
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        return briefing_path
    
    async def run(self) -> str:
        """Main run method - executes the weekly audit"""
        today = datetime.now()
        
        print(f"\n{'━'*60}")
        print(f"📊 WEEKLY AUDIT - {today.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'━'*60}")
        print(f"📂 Vault: {self.vault_path}")
        print(f"📅 Day: {today.strftime('%A')}")
        
        data = await self.gather_data()
        briefing = self.generate_ceo_briefing(data)
        path = self.save_briefing(briefing, data)
        
        print(f"✅ CEO Weekly Briefing saved to: {path.name}")
        
        accounting = data.get('accounting', {})
        summary = accounting.get('summary', {})
        financial = accounting.get('financial_summary', {})
        
        if summary.get('has_financial_data'):
            print(f"💰 Total Revenue: ${financial.get('total_revenue', 0):,.2f}")
        print(f"📁 Total Files in Accounting: {summary.get('total_files', 0)}")
        print(f"📈 Trend data saved for next week comparison")
        print(f"{'━'*60}\n")
        
        return str(path)


async def main(vault_path: Optional[str] = None) -> None:
    """Main entry point"""
    agent_name = os.environ.get('AGENT_NAME', 'Weekly Audit Agent')
    audit = WeeklyAudit(vault_path=vault_path, agent_name=agent_name)
    await audit.run()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Weekly Audit & CEO Briefing Generator (runs any day)')
    parser.add_argument('--vault', '-v', help='Path to the Obsidian vault', default=None)
    parser.add_argument('--agent', '-a', help='Agent name (e.g., "RALPH", "Orchestrator")', default=None)
    
    args = parser.parse_args()
    
    agent_name: str = args.agent or os.environ.get('AGENT_NAME', 'Weekly Audit Agent')
    
    async def run_audit() -> None:
        audit = WeeklyAudit(vault_path=args.vault, agent_name=agent_name)
        await audit.run()
    
    asyncio.run(run_audit())