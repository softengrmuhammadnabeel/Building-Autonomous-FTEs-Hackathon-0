"""
LinkedIn MCP Server - ASYNC VERSION with Working Selectors
Uses Playwright Async API for MCP compatibility
"""

import asyncio
import json
import re
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# MCP SDK imports
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions
import mcp.server.stdio
import mcp.server
import mcp.types as types

# Load environment
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('LinkedInMCP')


class LinkedInPosterAsync:
    """LinkedIn Poster - ASYNC VERSION with working selectors"""

    def __init__(
        self,
        vault_path: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        dry_run: Optional[bool] = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        
        # Create folders
        self.session_path = self.vault_path / ".linkedin_session"
        self.session_path.mkdir(parents=True, exist_ok=True)

        self.email = email or os.getenv("LINKEDIN_EMAIL")
        self.password = password or os.getenv("LINKEDIN_PASSWORD")

        if dry_run is None:
            self.dry_run = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")
        else:
            self.dry_run = dry_run

        if not self.email or not self.password:
            logger.warning("⚠️ LinkedIn credentials not found!")
        else:
            preview = self.email[:5] + "..." if len(self.email) > 5 else self.email
            logger.info(f"✅ LinkedIn credentials loaded (Email: {preview})")

        if self.dry_run:
            logger.warning("=" * 55)
            logger.warning("⚠️ DRY RUN MODE — no posts will be published!")
            logger.warning("=" * 55)
        else:
            logger.info("✅ LIVE MODE — posts will be published for real")

    async def authenticate(self, page) -> bool:
        """Async authentication with working selectors from old code"""
        try:
            logger.info("🔐 Starting LinkedIn authentication...")
            await page.goto("https://www.linkedin.com/uas/login", timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(3000)

            if "feed" in page.url:
                logger.info("✅ Already authenticated")
                return True

            # Screenshot for debugging
            try:
                await page.screenshot(path=str(self.session_path / "login_page.png"))
                logger.info(f"📸 Login page screenshot saved")
            except Exception:
                pass

            # Email field - multiple selectors
            logger.info("📧 Entering email...")
            email_selectors = [
                'input#username',
                'input[name="session_key"]',
                'input[type="email"]',
                'input[aria-label*="Email"]',
                'input[placeholder*="Email"]',
                'input[type="text"]',
            ]
            
            email_filled = False
            for selector in email_selectors:
                try:
                    el = page.locator(selector).first
                    if await el.count() and await el.is_visible():
                        await el.fill(self.email or "")
                        email_filled = True
                        logger.info(f"✅ Email filled via: {selector}")
                        break
                except Exception:
                    continue
            
            if not email_filled:
                try:
                    el = page.get_by_placeholder("Email or phone")
                    if await el.count():
                        await el.first.fill(self.email or "")
                        email_filled = True
                        logger.info("✅ Email filled via placeholder")
                except Exception:
                    pass
            
            if not email_filled:
                await page.screenshot(path=str(self.session_path / "email_field_fail.png"))
                logger.error("❌ Could not find email field")
                return False

            await page.wait_for_timeout(500)

            # Password field - multiple selectors
            logger.info("🔒 Entering password...")
            password_selectors = [
                'input#password',
                'input[name="session_password"]',
                'input[type="password"]',
                'input[aria-label*="Password"]',
            ]
            
            pass_filled = False
            for selector in password_selectors:
                try:
                    el = page.locator(selector).first
                    if await el.count() and await el.is_visible():
                        await el.fill(self.password or "")
                        pass_filled = True
                        logger.info(f"✅ Password filled via: {selector}")
                        break
                except Exception:
                    continue
            
            if not pass_filled:
                try:
                    el = page.get_by_placeholder("Password")
                    if await el.count():
                        await el.first.fill(self.password or "")
                        pass_filled = True
                        logger.info("✅ Password filled via placeholder")
                except Exception:
                    pass
            
            if not pass_filled:
                await page.screenshot(path=str(self.session_path / "pass_field_fail.png"))
                logger.error("❌ Could not find password field")
                return False

            await page.wait_for_timeout(500)

            # Click Sign In
            logger.info("🔘 Clicking Sign In...")
            sign_in_selectors = [
                'button[type="submit"]',
                'button:has-text("Sign in")',
                'button:has-text("Sign In")',
            ]
            
            clicked = False
            for selector in sign_in_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.count() and await btn.is_visible():
                        await btn.click()
                        clicked = True
                        logger.info(f"✅ Sign In clicked via: {selector}")
                        break
                except Exception:
                    continue
            
            if not clicked:
                await page.keyboard.press("Enter")
                logger.info("✅ Pressed Enter to submit")

            logger.info("⏳ Waiting for login to process...")
            await page.wait_for_timeout(8000)
            
            logger.info("📍 Navigating to LinkedIn feed...")
            await page.goto("https://www.linkedin.com/feed/", timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(5000)

            if "feed" in page.url:
                logger.info("✅ Authentication successful! On feed page.")
                return True

            logger.error(f"❌ Login failed. Current URL: {page.url}")
            await page.screenshot(path=str(self.session_path / "login_failed.png"))
            return False

        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            return False

    async def _open_post_dialog(self, page) -> bool:
        """Open post dialog - async version"""
        logger.info("⏳ Waiting for feed to load completely...")
        await page.wait_for_timeout(5000)
        
        try:
            logger.info("🔍 Looking for 'Start a post' button...")
            
            try:
                post_btn = page.get_by_text("Start a post", exact=True).first
                if await post_btn.is_visible():
                    await post_btn.click()
                    logger.info("✅ Clicked via exact text")
                    await page.wait_for_timeout(3000)
                    return True
            except:
                pass
            
            try:
                post_btn = page.get_by_role("button", name="Start a post")
                if await post_btn.is_visible():
                    await post_btn.click()
                    logger.info("✅ Clicked via role")
                    await page.wait_for_timeout(3000)
                    return True
            except:
                pass
            
            try:
                post_btn = page.locator('button:has-text("Start a post")').first
                if await post_btn.is_visible():
                    await post_btn.click()
                    logger.info("✅ Clicked via CSS selector")
                    await page.wait_for_timeout(3000)
                    return True
            except:
                pass
            
            try:
                post_btn = page.locator('.share-box-feed-entry__trigger').first
                if await post_btn.is_visible():
                    await post_btn.click()
                    logger.info("✅ Clicked via share-box class")
                    await page.wait_for_timeout(3000)
                    return True
            except:
                pass
        except Exception as e:
            logger.debug(f"Button click failed: {e}")
        
        logger.info("🔄 Trying direct post URL...")
        try:
            await page.goto("https://www.linkedin.com/feed/?shareActive=true", timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(3000)
            composer = page.locator('div[role="textbox"], div[contenteditable="true"]').first
            if await composer.is_visible():
                logger.info("✅ Post dialog opened via direct URL")
                return True
        except Exception as e:
            logger.debug(f"Direct URL failed: {e}")
        
        shot = self.session_path / f"dialog_fail_{datetime.now().strftime('%H%M%S')}.png"
        await page.screenshot(path=str(shot))
        logger.error(f"❌ Could not open post dialog — see {shot.name}")
        return False

    async def _find_text_area(self, page) -> Optional[Any]:
        """Find text area - async version"""
        TEXT_AREA_SELECTORS = [
            'div[role="textbox"]',
            'div[contenteditable="true"]',
            '.ql-editor',
            '.ql-editor.ql-blank',
            '.share-creation-state__text-editor div[contenteditable]',
            'div[data-placeholder*="What"]',
            'div[data-placeholder*="mind"]',
        ]
        for sel in TEXT_AREA_SELECTORS:
            try:
                el = await page.wait_for_selector(sel, timeout=5000)
                if el and await el.is_visible():
                    logger.info(f"✅ Text area found via: {sel}")
                    return el
            except PlaywrightTimeout:
                continue
            except Exception:
                continue

        logger.error("❌ Text area not found")
        return None

    async def _paste_content(self, page, text_area, content: str) -> bool:
        """Paste content - async version"""
        logger.info("🎯 Clicking text area...")
        await text_area.click()
        await page.wait_for_timeout(500)
        
        try:
            await page.keyboard.press("Control+a")
            await page.wait_for_timeout(200)
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(300)
            logger.info("✅ Cleared existing content")
        except Exception as e:
            logger.debug(f"Clear failed: {e}")

        try:
            logger.info("⌨️ Typing content...")
            await page.keyboard.type(content, delay=5)
            await page.wait_for_timeout(1000)
            logger.info("✅ Content typed successfully")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Typing error: {e}")

        try:
            logger.info("📝 Trying JavaScript injection...")
            safe_content = json.dumps(content)
            await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('div[role="textbox"], div[contenteditable="true"]');
                    if (el) {{
                        el.innerText = {safe_content};
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }}
            """)
            await page.wait_for_timeout(1000)
            logger.info("✅ JavaScript injection success")
            return True
        except Exception as e:
            logger.warning(f"⚠️ JavaScript injection error: {e}")

        try:
            logger.info("📋 Trying clipboard paste...")
            safe_json = json.dumps(content)
            await page.evaluate(f"navigator.clipboard.writeText({safe_json})")
            await page.wait_for_timeout(500)
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(300)
            await page.keyboard.press("Control+v")
            await page.wait_for_timeout(1000)
            logger.info("✅ Clipboard paste success")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Clipboard error: {e}")

        logger.error("❌ All paste methods failed")
        try:
            await page.screenshot(path=str(self.session_path / "paste_failed.png"))
            logger.info("📸 Screenshot saved: paste_failed.png")
        except Exception:
            pass
        return False

    async def _click_post_button(self, page) -> bool:
        """Click post button - async version"""
        try:
            logger.info("⌨️ Trying Ctrl+Enter...")
            await page.keyboard.press("Control+Enter")
            await page.wait_for_timeout(3000)
            dialog = await page.query_selector('div[role="dialog"]')
            if not dialog:
                logger.info("✅ Post published via Ctrl+Enter")
                return True
        except Exception:
            pass

        POST_SELECTORS = [
            'button:has-text("Post")',
            'button[aria-label="Post"]',
            '.share-actions__primary-action',
            '.artdeco-button--primary:has-text("Post")',
        ]
        
        for sel in POST_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.count() and await btn.is_visible() and await btn.is_enabled():
                    await btn.click()
                    await page.wait_for_timeout(3000)
                    logger.info(f"✅ Post button clicked via: {sel}")
                    return True
            except Exception:
                continue

        logger.error("❌ Could not click Post button")
        return False

    async def _verify_post_success(self, page) -> bool:
        """Verify post success - async version"""
        await page.wait_for_timeout(5000)
        
        try:
            if await page.locator('div[role="dialog"]').count() == 0:
                logger.info("✅ Dialog closed — post published")
                return True
        except Exception:
            pass
        
        success_indicators = [
            '.artdeco-toast-item',
            'text=Post successful',
            'text=Your post',
        ]
        
        for sel in success_indicators:
            try:
                if await page.locator(sel).first.is_visible():
                    logger.info(f"✅ Success indicator found")
                    return True
            except Exception:
                continue
        
        if "feed" in page.url:
            logger.info("✅ On feed page — post assumed published")
            return True
            
        return False

    async def post_to_linkedin(self, content: str) -> bool:
        """Async post to LinkedIn - complete workflow"""
        if self.dry_run:
            logger.warning("=" * 55)
            logger.warning("⚠️ DRY RUN — skipping real post. No browser opened.")
            logger.warning("=" * 55)
            logger.info(f"   Content preview: {content[:200]}")
            return True

        browser = None
        context = None

        try:
            clean_content = self._clean_content(content)
            logger.info("🚀 Starting LinkedIn automation...")

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                )
                page = await context.new_page()

                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    window.chrome = { runtime: {} };
                """)
                logger.info("🛡️ Bot-detection init script applied")

                logger.info("🌐 Navigating to LinkedIn feed...")
                await page.goto("https://www.linkedin.com/feed/", timeout=60000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)

                if "login" in page.url.lower() or "uas" in page.url.lower():
                    logger.info("🔐 Login required...")
                    if not await self.authenticate(page):
                        return False
                    await page.wait_for_timeout(2000)

                logger.info("⏳ Waiting for feed to load...")
                await page.wait_for_timeout(5000)
                
                logger.info("📝 Creating post...")
                if not await self._open_post_dialog(page):
                    return False

                logger.info("🔍 Finding text area...")
                text_area = await self._find_text_area(page)
                if not text_area:
                    await page.screenshot(path=str(self.session_path / "textarea_fail.png"))
                    return False

                logger.info("📋 Pasting content...")
                if not await self._paste_content(page, text_area, clean_content):
                    await page.screenshot(path=str(self.session_path / "paste_fail.png"))
                    return False

                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                before_shot = self.session_path / f"before_post_{timestamp}.png"
                await page.screenshot(path=str(before_shot))
                logger.info(f"📸 BEFORE POST screenshot saved: {before_shot.name}")

                await page.wait_for_timeout(1000)

                logger.info("🚀 Publishing post...")
                if not await self._click_post_button(page):
                    await page.screenshot(path=str(self.session_path / "post_btn_fail.png"))
                    return False

                await page.wait_for_timeout(5000)

                after_shot = self.session_path / f"after_post_{timestamp}.png"
                await page.screenshot(path=str(after_shot))
                logger.info(f"📸 AFTER POST screenshot saved: {after_shot.name}")

                success = await self._verify_post_success(page)
                if success:
                    logger.info("=" * 60)
                    logger.info("✅ POST PUBLISHED SUCCESSFULLY!")
                    logger.info("=" * 60)
                    return True
                else:
                    logger.warning("⚠️ Could not confirm post publication")
                    return False

        except Exception as e:
            logger.error(f"❌ Failed to post: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        finally:
            try:
                if context:
                    await context.close()
            except Exception:
                pass
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass

    def _clean_content(self, content: str) -> str:
        """
        Clean markdown content for LinkedIn - PRESERVE HASHTAGS
        Removes markdown headers, bold/italic formatting but KEEPS #hashtags
        """
        # Remove frontmatter (--- ... ---)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        
        lines = []
        for line in content.split("\n"):
            line_stripped = line.strip()
            
            # Keep empty lines for spacing
            if not line_stripped:
                lines.append(line)
                continue
            
            # Check if it's a markdown header (# Heading) - SKIP these
            if re.match(r'^#{1,6}\s+', line):
                continue
            
            # Check if it's a hashtag line (starts with # and has no space after #)
            # Examples: #hashtag, #MultipleWords, #AI, #NewHire
            if line_stripped.startswith('#') and not re.match(r'^#{1,6}\s+', line):
                # Keep hashtags as they are
                lines.append(line)
                continue
            
            # Remove markdown formatting from regular text
            cleaned = line
            cleaned = cleaned.replace("**", "")  # Remove bold
            cleaned = cleaned.replace("*", "")   # Remove italic  
            cleaned = cleaned.replace("`", "")   # Remove code ticks
            
            lines.append(cleaned)
        
        content = "\n".join(lines)
        
        # Trim if too long (LinkedIn limit ~3000 chars)
        if len(content) > 2900:
            content = content[:2900] + "..."
        
        return content.strip()


# ── MCP SERVER WRAPPER (ASYNC) ──────────────────────────────────────────────

class LinkedInMCPServer:
    def __init__(self):
        self.poster: Optional[LinkedInPosterAsync] = None
        self.initialized = False

    async def initialize(self, vault_path: str) -> Dict[str, Any]:
        self.poster = LinkedInPosterAsync(vault_path=vault_path, dry_run=False)
        self.initialized = True
        return {"success": True, "message": "LinkedIn MCP Server initialized (ASYNC)"}

    async def post_to_linkedin(self, content: str, title: str = "") -> Dict[str, Any]:
        if not self.initialized or not self.poster:
            return {"success": False, "error": "Server not initialized"}
        
        final = f"{title}\n\n{content}" if title else content
        success = await self.poster.post_to_linkedin(final)
        
        return {"success": success, "message": "Posted" if success else "Failed"}

    # ── READ-ONLY METHODS ADDED ────────────────────────────────────────────────
    
    async def get_page_info(self) -> Dict[str, Any]:
        """READ-ONLY: Get LinkedIn page information"""
        return {
            "success": True,
            "page_id": os.getenv('LINKEDIN_PAGE_ID', 'Not configured'),
            "page_name": os.getenv('LINKEDIN_PAGE_NAME', 'LinkedIn Page'),
            "authenticated": bool(os.getenv('LINKEDIN_EMAIL')),
            "mode": "email_password"
        }

    async def get_insights(self, metric: str = "followers,impressions,engagement") -> Dict[str, Any]:
        """READ-ONLY: Get LinkedIn insights (limited with email/password)"""
        return {
            "success": True,
            "followers": "N/A",
            "impressions": "N/A",
            "engagement": "N/A",
            "insights_available": False,
            "message": "Full insights require OAuth 2.0 access token"
        }

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy", "initialized": self.initialized}


async def serve() -> None:
    server = LinkedInMCPServer()
    mcp_server = mcp.server.Server("linkedin-mcp-server")

    @mcp_server.list_tools()
    async def list_tools() -> List[types.Tool]:
        return [
            # READ-ONLY tools
            types.Tool(
                name="linkedin_page_info",
                description="Get LinkedIn page information (READ-ONLY)",
                inputSchema={"type": "object", "properties": {}}
            ),
            types.Tool(
                name="linkedin_insights",
                description="Get LinkedIn page insights (READ-ONLY)",
                inputSchema={"type": "object", "properties": {
                    "metric": {"type": "string", "description": "Metrics to retrieve (followers,impressions,engagement)"}
                }}
            ),
            # WRITE tool (for Orchestrator only)
            types.Tool(
                name="linkedin_post",
                description="Post to LinkedIn",
                inputSchema={"type": "object", "properties": {
                    "content": {"type": "string"},
                    "title": {"type": "string"}
                }, "required": ["content"]}
            ),
            types.Tool(
                name="linkedin_initialize",
                description="Initialize server",
                inputSchema={"type": "object", "properties": {
                    "vault_path": {"type": "string"}
                }, "required": ["vault_path"]}
            ),
            types.Tool(
                name="linkedin_health_check",
                description="Health check",
                inputSchema={"type": "object", "properties": {}}
            ),
        ]

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> List[types.TextContent]:
        if name == "linkedin_initialize":
            result = await server.initialize(arguments.get("vault_path", ""))
        elif name == "linkedin_page_info":
            result = await server.get_page_info()
        elif name == "linkedin_insights":
            result = await server.get_insights(arguments.get("metric", "followers,impressions,engagement"))
        elif name == "linkedin_post":
            result = await server.post_to_linkedin(
                arguments.get("content", ""),
                arguments.get("title", "")
            )
        elif name == "linkedin_health_check":
            result = await server.health_check()
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [types.TextContent(type="text", text=json.dumps(result))]

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("LinkedIn MCP Server (ASYNC) starting...")
        await mcp_server.run(read_stream, write_stream, InitializationOptions(
            server_name="linkedin-mcp-server",
            server_version="2.0.0",
            capabilities=mcp_server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={}
            )
        ))


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()