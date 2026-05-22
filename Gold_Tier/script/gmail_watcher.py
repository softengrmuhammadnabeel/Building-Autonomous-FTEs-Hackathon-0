"""
Gmail MCP Server - Automatic Email Monitoring with MCP (PURE ASYNC)
Automatically checks Gmail every 2 minutes and creates action files in Needs_Action.
Real-time email detection - shows actual unread count only from PRIMARY category.
"""

import os
import sys
import json
import base64
import logging
import asyncio
import signal
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from email.utils import parsedate_to_datetime
from email.mime.text import MIMEText

from dotenv import load_dotenv
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Google imports
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / '.env')

# Setup logging with timestamp - ONLY ONE HANDLER
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stderr  # Send to stderr to avoid breaking MCP protocol
)
logger = logging.getLogger('GmailMCP')

# Suppress verbose googleapiclient cache messages
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# Create MCP Server instance
server = Server("gmail-mcp-server")

# Configuration from .env
GMAIL_CREDENTIALS_PATH: str = os.getenv("GMAIL_CREDENTIALS_PATH", "")
if not GMAIL_CREDENTIALS_PATH:
    possible_paths = [
        PROJECT_ROOT / 'credentials.json',
        SCRIPT_DIR / 'credentials.json',
        PROJECT_ROOT / 'gmail_token.json',
    ]
    for path in possible_paths:
        if path.exists():
            GMAIL_CREDENTIALS_PATH = str(path)
            break

VAULT_PATH: str = os.getenv("VAULT_PATH", "")
if not VAULT_PATH:
    VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "")
if not VAULT_PATH:
    possible_vaults = [
        PROJECT_ROOT / 'AI_Employee_Vault',
        PROJECT_ROOT / '.qwen' / 'AI_Employee_Vault',
        SCRIPT_DIR / 'AI_Employee_Vault'
    ]
    for path in possible_vaults:
        if path.exists():
            VAULT_PATH = str(path)
            break
    else:
        VAULT_PATH = str(PROJECT_ROOT / 'AI_Employee_Vault')

# Get environment variables with defaults
CHECK_INTERVAL: int = int(os.getenv("WATCHER_CHECK_INTERVAL", "120"))
MAX_EMAILS_PER_CHECK: int = int(os.getenv("GMAIL_MAX_EMAILS", "10"))


class GmailMCPWatcher:
    """
    Gmail Watcher with MCP Server support (PURE ASYNC).
    Real-time email checking - shows actual unread count only from PRIMARY tab.
    """

    def __init__(self):
        self.vault_path: Path = Path(VAULT_PATH).resolve()
        self.credentials_path: str = GMAIL_CREDENTIALS_PATH
        self.needs_action: Path = self.vault_path / 'Needs_Action'
        self.logs_dir: Path = self.vault_path / '.ai_employee_logs'
        self.processed_ids_file: Path = self.logs_dir / 'gmail_processed_ids.txt'

        self.processed_ids: set = set()
        self.service: Any = None
        self.creds: Any = None
        self.token_path: Optional[Path] = None
        self.running: bool = False
        self.auto_task: Optional[asyncio.Task] = None
        self.last_unread_count: int = 0
        self.shutdown_requested: bool = False
        self.is_stopping: bool = False

        # Create directories
        self.needs_action.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Load processed IDs
        self._load_processed_ids()

        logger.info(f"✅ Gmail MCP Watcher initialized")
        logger.info(f"  Vault: {self.vault_path}")
        logger.info(f"  Needs_Action: {self.needs_action}")
        logger.info(f"  Check interval: {CHECK_INTERVAL}s")

    def _load_processed_ids(self) -> None:
        """Load previously processed email IDs."""
        if self.processed_ids_file.exists():
            try:
                content = self.processed_ids_file.read_text().strip()
                if content:
                    self.processed_ids = set(content.split('\n'))
                    logger.info(f"Loaded {len(self.processed_ids)} processed email IDs")
            except Exception as e:
                logger.warning(f'Failed to load processed IDs: {e}')

    def _save_processed_ids(self) -> None:
        """Save processed email IDs."""
        try:
            ids_list = list(self.processed_ids)[-1000:]
            self.processed_ids_file.write_text('\n'.join(ids_list))
        except Exception as e:
            logger.warning(f'Failed to save processed IDs: {e}')

    async def authenticate(self) -> Dict[str, Any]:
        """Authenticate with Gmail API (async wrapper for blocking calls)."""
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            import google.auth.transport.requests as auth_requests

            if not self.credentials_path or not Path(self.credentials_path).exists():
                return {'success': False, 'error': f'Credentials not found at: {self.credentials_path}'}

            creds_file = Path(self.credentials_path)
            self.token_path = creds_file.parent / 'gmail_token.json'
            SCOPES = ['https://www.googleapis.com/auth/gmail.modify',
                      'https://www.googleapis.com/auth/gmail.readonly',
                      'https://www.googleapis.com/auth/gmail.send']

            if self.token_path.exists():
                try:
                    self.creds = await asyncio.to_thread(
                        Credentials.from_authorized_user_file,
                        str(self.token_path), SCOPES
                    )
                    
                    if self.creds and self.creds.valid:
                        self.service = await asyncio.to_thread(build, 'gmail', 'v1', credentials=self.creds)
                        return {'success': True, 'message': 'Authenticated from token'}

                    if self.creds and self.creds.expired and self.creds.refresh_token:
                        request = auth_requests.Request()
                        await asyncio.to_thread(self.creds.refresh, request)
                        await asyncio.to_thread(
                            lambda: open(str(self.token_path), 'w').write(self.creds.to_json())
                        )
                        self.service = await asyncio.to_thread(build, 'gmail', 'v1', credentials=self.creds)
                        return {'success': True, 'message': 'Token refreshed'}
                except Exception as e:
                    logger.warning(f'Token load failed: {e}')

            logger.info('Starting OAuth flow - browser will open...')
            
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            self.creds = await asyncio.to_thread(flow.run_local_server, port=0)

            await asyncio.to_thread(
                lambda: open(str(self.token_path), 'w').write(self.creds.to_json())
            )

            self.service = await asyncio.to_thread(build, 'gmail', 'v1', credentials=self.creds)
            return {'success': True, 'message': 'OAuth successful'}

        except Exception as e:
            logger.error(f'Authentication failed: {e}')
            return {'success': False, 'error': str(e)}

    async def get_primary_inbox_unread_count(self) -> int:
        """Get accurate unread count only from PRIMARY category."""
        if not self.service:
            return 0

        try:
            results = await asyncio.to_thread(
                self.service.users().messages().list,
                userId='me',
                q='is:unread category:primary',
                maxResults=500
            )

            messages = await asyncio.to_thread(results.execute)
            return len(messages.get('messages', []))

        except Exception as e:
            logger.error(f'Error getting primary inbox unread count: {e}')
            return 0

    async def check_for_updates(self, max_emails: Optional[int] = None) -> Tuple[List[Dict], int]:
        """Check for unread emails in PRIMARY category."""
        if not self.service:
            auth_result = await self.authenticate()
            if not auth_result.get('success'):
                return [], 0

        try:
            limit: int = max_emails if max_emails is not None else MAX_EMAILS_PER_CHECK

            results = await asyncio.to_thread(
                self.service.users().messages().list,
                userId='me',
                q='is:unread category:primary',
                maxResults=limit
            )
            messages = await asyncio.to_thread(results.execute)
            messages_list = messages.get('messages', [])

            all_results = await asyncio.to_thread(
                self.service.users().messages().list,
                userId='me',
                q='is:unread category:primary',
                maxResults=500
            )
            all_messages = await asyncio.to_thread(all_results.execute)
            total_unread = len(all_messages.get('messages', []))

            new_emails = []
            for msg in messages_list:
                if msg['id'] not in self.processed_ids:
                    full_msg = await asyncio.to_thread(
                        self.service.users().messages().get,
                        userId='me', id=msg['id'], format='full'
                    )
                    full_msg_data = await asyncio.to_thread(full_msg.execute)
                    new_emails.append(full_msg_data)

            return new_emails, total_unread

        except Exception as e:
            logger.error(f'Error checking emails: {e}')
            return [], 0

    def _extract_email_data(self, message: Dict) -> Dict[str, str]:
        """Extract email data."""
        try:
            payload = message.get('payload', {})
            headers_list = payload.get('headers', [])
            headers = {h['name']: h['value'] for h in headers_list}

            body = ''
            if 'parts' in payload:
                for part in payload['parts']:
                    if part.get('mimeType') == 'text/plain':
                        body_data = part.get('body', {}).get('data', '')
                        if body_data:
                            body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                            break
            elif 'body' in payload:
                body_data = payload['body'].get('data', '')
                if body_data:
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')

            date_str = headers.get('Date', '')
            try:
                date_obj = parsedate_to_datetime(date_str)
                received = date_obj.isoformat()
            except Exception:
                received = datetime.now().isoformat()

            return {
                'message_id': message.get('id', 'unknown'),
                'thread_id': message.get('threadId', 'unknown'),
                'from': headers.get('From', 'Unknown'),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', 'No Subject'),
                'date': received,
                'snippet': message.get('snippet', ''),
                'body': body[:3000],
            }
        except Exception as e:
            return {'message_id': 'error', 'subject': f'Error: {e}', 'from': '', 'to': '', 'date': '', 'snippet': '', 'body': '', 'thread_id': ''}

    def _safe_filename(self, text: str) -> str:
        """Create safe filename."""
        safe = "".join(c for c in text if c.isalnum() or c in ' _-')
        return safe.strip() or "unnamed"

    def _create_action_file_sync(self, message: Dict, suppress_log: bool = False) -> Optional[Path]:
        """Create action file in Needs_Action folder."""
        try:
            email_data = self._extract_email_data(message)

            if email_data.get('message_id') in self.processed_ids:
                return None

            safe_subject = self._safe_filename(email_data.get('subject', 'no_subject'))[:50]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"EMAIL_{timestamp}_{safe_subject}.md"

            snippet_lower = email_data.get('snippet', '').lower()
            subject_lower = email_data.get('subject', '').lower()
            priority_keywords = ['important', 'urgent', 'asap', 'critical']
            is_high = any(kw in snippet_lower or kw in subject_lower for kw in priority_keywords)
            priority = 'high' if is_high else 'normal'

            content = f'''---
type: email
from: "{email_data.get('from', 'Unknown')}"
to: "{email_data.get('to', '')}"
subject: "{email_data.get('subject', 'No Subject')}"
received: {email_data.get('date', datetime.now().isoformat())}
priority: {priority}
status: pending
message_id: {email_data.get('message_id', 'unknown')}
thread_id: {email_data.get('thread_id', 'unknown')}
created: {datetime.now().isoformat()}
---

# Email: {email_data.get('subject', 'No Subject')}

## From
{email_data.get('from', 'Unknown')}

## To
{email_data.get('to', '')}

## Received
{email_data.get('date', datetime.now().isoformat())}

## Snippet
{email_data.get('snippet', '')}

## Body

{email_data.get('body', '')[:2000]}

## Suggested Actions
- [ ] Reply to sender
- [ ] Archive after processing

---
*Auto-created by Gmail MCP Server on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
'''

            filepath = self.needs_action / filename
            filepath.write_text(content, encoding='utf-8')

            self.processed_ids.add(email_data.get('message_id', 'unknown'))
            self._save_processed_ids()

            if not suppress_log:
                logger.debug(f"Created: {filename}")
            return filepath

        except Exception as e:
            logger.error(f'Failed to create action file: {e}')
            return None

    async def process_all_new_emails(self, max_emails: Optional[int] = None) -> Dict[str, Any]:
        """Process all new emails."""
        new_emails, total_unread = await self.check_for_updates(max_emails)

        created_files = []
        for email in new_emails:
            filepath = await asyncio.to_thread(
                self._create_action_file_sync, email, True
            )
            if filepath:
                created_files.append(str(filepath))

        return {
            'success': True,
            'emails_found': total_unread,
            'new_emails_count': len(new_emails),
            'action_files_created': len(created_files),
            'files': created_files
        }

    async def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        current_unread = await self.get_primary_inbox_unread_count()

        return {
            'success': True,
            'authenticated': self.service is not None,
            'vault_path': str(self.vault_path),
            'needs_action_path': str(self.needs_action),
            'processed_emails_count': len(self.processed_ids),
            'auto_running': self.running,
            'check_interval': CHECK_INTERVAL,
            'current_primary_inbox_unread': current_unread
        }

    async def start_auto_watcher(self) -> Dict[str, Any]:
        """Start automatic email checking in background."""
        if self.running:
            return {'success': False, 'message': 'Auto watcher already running'}

        self.running = True
        self.shutdown_requested = False
        self.is_stopping = False
        self.auto_task = asyncio.create_task(self._auto_loop_async())

        return {'success': True, 'message': f'Auto watcher started (interval: {CHECK_INTERVAL}s)'}

    async def stop_auto_watcher(self) -> Dict[str, Any]:
        """Stop automatic email checking."""
        if self.is_stopping:
            return {'success': True, 'message': 'Already stopping'}

        self.is_stopping = True
        self.running = False
        self.shutdown_requested = True

        if self.auto_task and not self.auto_task.done():
            self.auto_task.cancel()
            try:
                await self.auto_task
            except asyncio.CancelledError:
                pass

        return {'success': True, 'message': 'Auto watcher stopped'}

    async def _auto_loop_async(self) -> None:
        """Background loop for automatic email checking with logger output."""
        await self.authenticate()

        while self.running and not self.shutdown_requested:
            try:
                logger.info(f"🔍 Checking Inbox...")
                
                new_emails, total_unread = await self.check_for_updates()

                if total_unread > 0:
                    logger.info(f"📧 Found {total_unread} unread email(s) in Inbox")
                else:
                    logger.info(f"📧 No unread emails in Inbox")

                new_count = 0
                created_files_list = []
                for email in new_emails:
                    if not self.running or self.shutdown_requested:
                        break
                    filepath = await asyncio.to_thread(
                        self._create_action_file_sync, email, True
                    )
                    if filepath:
                        new_count += 1
                        created_files_list.append(Path(filepath).name)
                    await asyncio.sleep(0.1)

                for filename in created_files_list:
                    logger.info(f"✅ Created: {filename}")

                if new_count > 0:
                    logger.info(f"✨ Processed {new_count} new email(s) → Needs_Action folder")
                else:
                    if total_unread > 0:
                        logger.info(f"✨ No new emails to process (already processed before)")
                    else:
                        logger.info(f"✨ No new emails to process")
                        
                print("", file=sys.stderr)        

                for _ in range(CHECK_INTERVAL):
                    if not self.running or self.shutdown_requested:
                        break
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.shutdown_requested:
                    logger.error(f'Auto watcher error: {e}')
                await asyncio.sleep(5)

    # ✅ Send Email Method
    async def send_email(self, to: str, subject: str, body: str, in_reply_to: Optional[str] = None) -> Dict[str, Any]:
        """
        Send an email via Gmail API.
        
        Args:
            to: Recipient email address
            subject: Email subject line
            body: Email body content (plain text)
            in_reply_to: Optional message ID to reply to (for threading)
        
        Returns:
            Dict with success status and message details
        """
        if not self.service:
            auth_result = await self.authenticate()
            if not auth_result.get('success'):
                return {'success': False, 'error': 'Not authenticated', 'method': 'mcp'}

        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            if in_reply_to:
                message['In-Reply-To'] = in_reply_to
                message['References'] = in_reply_to
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            send_body = {'raw': raw_message}
            
            if in_reply_to:
                try:
                    original_msg = await asyncio.to_thread(
                        self.service.users().messages().get,
                        userId='me', id=in_reply_to, format='metadata'
                    )
                    msg_data = await asyncio.to_thread(original_msg.execute)
                    send_body['threadId'] = msg_data.get('threadId')
                    logger.info(f"Sending reply in thread: {send_body['threadId']}")
                except Exception as e:
                    logger.warning(f"Could not get thread ID for reply: {e}")
            
            sent = await asyncio.to_thread(
                self.service.users().messages().send,
                userId='me', body=send_body
            )
            result = await asyncio.to_thread(sent.execute)
            
            logger.info(f"Email sent successfully to {to} - Message ID: {result.get('id')}")
            
            return {
                'success': True,
                'message_id': result.get('id'),
                'thread_id': result.get('threadId'),
                'method': 'mcp'
            }
            
        except HttpError as e:
            error_msg = f'Gmail API error: {e}'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg, 'method': 'mcp'}
        except Exception as e:
            error_msg = f'Failed to send email: {e}'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg, 'method': 'mcp'}

    # ✅ Mark Email as Read Method
    async def mark_email_read(self, message_id: str) -> Dict[str, Any]:
        """Mark an email as read (remove UNREAD label)."""
        if not self.service:
            auth_result = await self.authenticate()
            if not auth_result.get('success'):
                return {'success': False, 'error': 'Not authenticated'}

        try:
            await asyncio.to_thread(
                self.service.users().messages().modify,
                userId='me', id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            )
            logger.info(f"Marked message {message_id} as read")
            return {'success': True, 'message_id': message_id}
        except Exception as e:
            logger.error(f"Failed to mark email as read: {e}")
            return {'success': False, 'error': str(e)}


# Initialize global watcher
gmail_watcher = GmailMCPWatcher()


# ── MCP Tool Definitions ─────────────────────────────────────────────────────

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List all available MCP tools."""
    return [
        types.Tool(
            name="gmail_authenticate",
            description="Authenticate with Gmail API",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        types.Tool(
            name="gmail_check_updates",
            description="Check for unread emails in PRIMARY Inbox only",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_emails": {"type": "integer", "description": "Max emails to check", "default": MAX_EMAILS_PER_CHECK}
                },
                "required": []
            }
        ),
        types.Tool(
            name="gmail_process_emails",
            description="Process unread emails from PRIMARY Inbox and create action files",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_emails": {"type": "integer", "description": "Max emails to process", "default": MAX_EMAILS_PER_CHECK}
                },
                "required": []
            }
        ),
        types.Tool(
            name="gmail_status",
            description="Get Gmail watcher status including current PRIMARY Inbox unread count",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        types.Tool(
            name="gmail_start_auto",
            description="Start automatic email checking (every 2 minutes) - PRIMARY Inbox only",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        types.Tool(
            name="gmail_stop_auto",
            description="Stop automatic email checking",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        # ✅ Send Email Tool (main)
        types.Tool(
            name="gmail_send_email",
            description="Send an email via Gmail API",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body content (plain text)"},
                    "in_reply_to": {"type": "string", "description": "Optional: Message ID to reply to"}
                },
                "required": ["to", "subject", "body"]
            }
        ),
        
        # ✅ Send Reply Tool (RENAMED from send_reply to gmail_send_email - keeping for compatibility)
        # types.Tool(
        #     name="gmail_send_email",  # ✅ Name changed from "send_reply" to "gmail_send_email"
        #     description="Send an email reply (compatible with orchestrator)",
        #     inputSchema={
        #         "type": "object",
        #         "properties": {
        #             "message_id": {"type": "string", "description": "Original message ID to reply to"},
        #             "to": {"type": "string", "description": "Recipient email address"},
        #             "subject": {"type": "string", "description": "Email subject line"},
        #             "body": {"type": "string", "description": "Email body content"}
        #         },
        #         "required": ["to", "subject", "body"]
        #     }
        # ),
        
        # ✅ Mark Email as Read Tool
        types.Tool(
            name="gmail_mark_read",
            description="Mark an email as read (remove UNREAD label)",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Gmail message ID to mark as read"}
                },
                "required": ["message_id"]
            }
        ),
        # ✅ Mark Email as Read Tool (short name for orchestrator)
        types.Tool(
            name="mark_read",
            description="Mark an email as read (compatible with orchestrator)",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Gmail message ID to mark as read"}
                },
                "required": ["message_id"]
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None
) -> List[types.TextContent]:
    """Handle MCP tool calls."""
    if arguments is None:
        arguments = {}

    try:
        if name == "gmail_authenticate":
            result = await gmail_watcher.authenticate()
        elif name == "gmail_check_updates":
            max_emails = arguments.get("max_emails", MAX_EMAILS_PER_CHECK)
            new_emails, total_unread = await gmail_watcher.check_for_updates(max_emails)
            email_summaries = []
            for email in new_emails[:10]:
                data = gmail_watcher._extract_email_data(email)
                email_summaries.append({
                    'from': data.get('from', 'Unknown'),
                    'subject': data.get('subject', 'No Subject'),
                    'snippet': data.get('snippet', '')[:100]
                })
            result = {
                'success': True,
                'total_unread': total_unread,
                'new_emails_count': len(new_emails),
                'emails': email_summaries
            }
        elif name == "gmail_process_emails":
            max_emails = arguments.get("max_emails", MAX_EMAILS_PER_CHECK)
            result = await gmail_watcher.process_all_new_emails(max_emails)
        elif name == "gmail_status":
            result = await gmail_watcher.get_status()
        elif name == "gmail_start_auto":
            result = await gmail_watcher.start_auto_watcher()
        elif name == "gmail_stop_auto":
            result = await gmail_watcher.stop_auto_watcher()
        # ✅ Handle gmail_send_email
        elif name == "gmail_send_email":
            to = arguments.get("to")
            subject = arguments.get("subject")
            body = arguments.get("body")
            in_reply_to = arguments.get("in_reply_to")
            
            if not to or not subject or not body:
                result = {'success': False, 'error': 'Missing required parameters: to, subject, body'}
            else:
                result = await gmail_watcher.send_email(to, subject, body, in_reply_to)
        # ✅ Handle gmail_mark_read
        elif name == "gmail_mark_read":
            message_id = arguments.get("message_id")
            if not message_id:
                result = {'success': False, 'error': 'Missing required parameter: message_id'}
            else:
                result = await gmail_watcher.mark_email_read(message_id)
        # ✅ Handle mark_read (short name for orchestrator)
        elif name == "mark_read":
            message_id = arguments.get("message_id")
            if not message_id:
                result = {'success': False, 'error': 'Missing required parameter: message_id'}
            else:
                result = await gmail_watcher.mark_email_read(message_id)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


# ── Main Entry Point ─────────────────────────────────────────────────────────

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    logger.info("🛑 Received shutdown signal. Stopping gracefully...")
    sys.exit(0)


async def main() -> None:
    """Run MCP server."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    auto_start = "--auto" in sys.argv

    if auto_start:
        logger.info("🤖 Auto mode enabled - starting real-time email checking...")
        logger.info("   💡 Press Ctrl+C to stop gracefully")
        print("", file=sys.stderr)
        await gmail_watcher.start_auto_watcher()
    else:
        logger.info("💡 Tip: Run with --auto to enable automatic email checking")
        logger.info("   Example: python gmail_watcher.py --auto")
        print("", file=sys.stderr)

    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="gmail-mcp-server",
                    server_version="2.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except KeyboardInterrupt:
        sys.exit(0)
    finally:
        if gmail_watcher and not getattr(gmail_watcher, 'is_stopping', False):
            await gmail_watcher.stop_auto_watcher()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass