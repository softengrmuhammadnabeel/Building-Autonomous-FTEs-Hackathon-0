"""
Gmail Watcher Module - Silver Tier
Monitors Gmail Inbox for unread emails and creates action files.
"""

import os
import sys
import base64
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from email.utils import parsedate_to_datetime

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Add script directory to path
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from base_watcher import BaseWatcher


class GmailWatcher(BaseWatcher):
    """Watches Gmail Inbox for unread messages."""

    def __init__(
        self,
        vault_path: str = None, # type: ignore
        credentials_path: str = None, # type: ignore
        check_interval: int = 120,
        max_emails_per_check: int = 10
    ):
        if vault_path is None:
            vault_path = os.getenv('VAULT_PATH')
        
        if not vault_path:
            raise ValueError("vault_path required. Set VAULT_PATH in .env")
        
        # Disable base watcher logger
        super().__init__(vault_path, check_interval)
        self.logger.disabled = True

        if credentials_path is None:
            credentials_path = os.getenv('GMAIL_CREDENTIALS_PATH')

        self.credentials_path = credentials_path
        self.max_emails_per_check = max_emails_per_check
        self.service = None
        self.processed_ids_file = Path(vault_path) / 'Logs' / 'gmail_processed_ids.txt'
        self.processed_ids = set()
        self._load_processed_ids()

    def _load_processed_ids(self):
        if self.processed_ids_file.exists():
            try:
                content = self.processed_ids_file.read_text().strip()
                if content:
                    self.processed_ids = set(content.split('\n'))
            except Exception:
                self.processed_ids = set()

    def _save_processed_ids(self):
        try:
            ids_list = list(self.processed_ids)[-1000:]
            self.processed_ids_file.write_text('\n'.join(ids_list))
        except Exception:
            pass
    
    def _authenticate(self) -> bool:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            import google.auth.transport.requests as auth_requests
            
            if not self.credentials_path or not Path(self.credentials_path).exists():
                print(f"[ERROR] Credentials not found")
                return False

            self.token_path = Path(self.credentials_path).parent / 'gmail_token.json'

            if self.token_path.exists():
                try:
                    self.creds = Credentials.from_authorized_user_file(
                        str(self.token_path),
                        ['https://www.googleapis.com/auth/gmail.modify']
                    )
                    
                    if self.creds and self.creds.valid:
                        self.service = build('gmail', 'v1', credentials=self.creds)
                        return True
                    
                    if self.creds and self.creds.expired and self.creds.refresh_token:
                        request = auth_requests.Request()
                        self.creds.refresh(request)
                        with open(str(self.token_path), 'w') as token_file:
                            token_file.write(self.creds.to_json())
                        self.service = build('gmail', 'v1', credentials=self.creds)
                        return True
                except Exception:
                    pass

            print("[INFO] Opening browser for authorization...")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path),
                ['https://www.googleapis.com/auth/gmail.modify']
            )
            
            self.creds = flow.run_local_server(port=0)
            
            with open(str(self.token_path), 'w') as token_file:
                token_file.write(self.creds.to_json())
            
            self.service = build('gmail', 'v1', credentials=self.creds)
            return True

        except Exception:
            return False

    def check_for_updates(self) -> List[Dict[str, Any]]:
        if not self.service:
            if not self._authenticate():
                return []

        try:
            results = self.service.users().messages().list( # type: ignore
                userId='me',
                q='is:unread category:primary',
                maxResults=self.max_emails_per_check
            ).execute()

            messages = results.get('messages', [])

            new_emails = []
            for msg in messages:
                if msg['id'] not in self.processed_ids:
                    full_msg = self.service.users().messages().get( # type: ignore
                        userId='me',
                        id=msg['id'],
                        format='full'
                    ).execute()
                    new_emails.append(full_msg)

            return new_emails

        except Exception:
            return []

    def _extract_email_data(self, message: Dict) -> Dict[str, str]:
        payload = message.get('payload', {})
        headers = {h['name']: h['value'] for h in payload.get('headers', [])}

        body = ''
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain':
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                        break
        elif 'body' in payload:
            body_data = payload['body'].get('data', '')
            if body_data:
                body = base64.urlsafe_b64decode(body_data).decode('utf-8')

        date_str = headers.get('Date', '')
        try:
            date_obj = parsedate_to_datetime(date_str)
            received = date_obj.isoformat()
        except Exception:
            received = datetime.now().isoformat()

        return {
            'message_id': message.get('id', 'unknown'),
            'from': headers.get('From', 'Unknown'),
            'to': headers.get('To', ''),
            'subject': headers.get('Subject', 'No Subject'),
            'date': received,
            'snippet': message.get('snippet', ''),
            'body': body[:2000],
        }

    def create_action_file(self, item: Dict[str, Any]) -> Optional[Path]:
        try:
            email_data = self._extract_email_data(item)

            if email_data['message_id'] in self.processed_ids:
                return None

            safe_subject = self.safe_filename(email_data['subject'])[:50]
            filename = f"EMAIL_{email_data['message_id']}_{safe_subject}.md"
            priority = 'high' if 'important' in email_data.get('snippet', '').lower() else 'normal'

            content = f'''---
type: email
from: "{email_data['from']}"
subject: "{email_data['subject']}"
received: {email_data['date']}
priority: {priority}
status: pending
message_id: {email_data['message_id']}
---

# Email: {email_data['subject']}

**From:** {email_data['from']}
**Date:** {email_data['date']}

## Snippet
{email_data['snippet']}

## Body
{email_data['body']}

## Actions
- [ ] Reply
- [ ] Forward
- [ ] Archive
'''

            filepath = self.needs_action / filename
            filepath.write_text(content, encoding='utf-8')

            self.processed_ids.add(email_data['message_id'])
            self._save_processed_ids()

            return filepath

        except Exception:
            return None

    def run(self):
        print("="*50)
        print("  GMAIL INBOX WATCHER")
        print("="*50)
        print(f"  Vault Path:     {self.vault_path}")
        print(f"  Needs Action:   {self.needs_action}")
        print(f"  Check Interval: {self.check_interval} seconds")
        print("="*50 + "\n")

        if not self._authenticate():
            print("[ERROR] Authentication failed")
            return

        print("[READY] Watching Gmail Inbox...\n")

        while True:
            try:
                current = datetime.now().strftime('%H:%M:%S')
                emails = self.check_for_updates()

                if emails:
                    print(f"[{current}] 📧 Found {len(emails)} new email(s)")
                    for mail in emails:
                        email_data = self._extract_email_data(mail)
                        print(f"      From: {email_data['from']}")
                        print(f"      Subject: {email_data['subject']}")
                        result = self.create_action_file(mail)
                        if result:
                            print(f"      ✓ Saved to: Needs_Action/{result.name}")
                    print("")
                else:
                    print(f"[{current}] No new emails in Inbox")

                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Stopped")
                break
            except Exception:
                time.sleep(self.check_interval)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Gmail Inbox Watcher')
    parser.add_argument('--vault', type=str, default=os.getenv('VAULT_PATH'))
    parser.add_argument('--credentials', type=str, default=os.getenv('GMAIL_CREDENTIALS_PATH'))
    parser.add_argument('--interval', type=int, default=int(os.getenv('WATCHER_CHECK_INTERVAL', '120')))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--clear-history', action='store_true')

    args = parser.parse_args()

    if not args.vault:
        print("[ERROR] VAULT_PATH not set in .env")
        return

    watcher = GmailWatcher(
        vault_path=args.vault,
        credentials_path=args.credentials,
        check_interval=args.interval
    )

    if args.clear_history:
        if watcher.processed_ids_file.exists():
            watcher.processed_ids_file.unlink()
            print("[OK] History cleared")
        return

    if args.once:
        if watcher._authenticate():
            print("[OK] Authentication successful")
            emails = watcher.check_for_updates()
            print(f"[INFO] Found {len(emails)} unread emails")
    else:
        watcher.run()


if __name__ == '__main__':
    main()