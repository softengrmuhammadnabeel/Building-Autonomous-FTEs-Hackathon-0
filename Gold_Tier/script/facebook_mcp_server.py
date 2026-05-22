"""
Facebook MCP Server - Graph API Version
Pure MCP server for orchestrator integration
"""

import sys
import os
import json
import logging
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Load environment
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / '.env')

# Setup logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # ✅ CRITICAL: Send logs to stderr, not stdou
)
logger = logging.getLogger('FacebookMCP')

# Create MCP Server instance
server = Server("facebook-mcp-server")

# Facebook Graph API configuration
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
GRAPH_API_BASE = "https://graph.facebook.com/v18.0"


class FacebookGraphAPI:
    """Facebook Graph API wrapper for page posting"""

    def __init__(self, access_token: str, page_id: str):
        self.access_token = access_token
        self.page_id = page_id
        self.dry_run = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")
        logger.info(f"Facebook Graph API initialized (Dry Run: {self.dry_run})")

    def post_to_page(self, message: str, image_url: Optional[str] = None) -> Dict[str, Any]:
        """Post to Facebook Page using Graph API"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would post to page {self.page_id}: {message[:100]}...")
            return {
                'status': 'dry_run',
                'message': 'Would post to Facebook',
                'content_preview': message[:200]
            }

        try:
            url = f"{GRAPH_API_BASE}/{self.page_id}/feed"
            params = {
                "access_token": self.access_token,
                "message": message
            }

            response = requests.post(url, data=params)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Successfully posted to Facebook. Post ID: {result.get('id')}")

            return {
                'success': True,
                'post_id': result.get('id'),
                'message': message[:200]
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook API error: {e}")
            error_detail = None
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.text
                except Exception:
                    error_detail = "Could not read response text"
            return {
                'success': False,
                'error': str(e),
                'error_detail': error_detail
            }

    def get_page_info(self) -> Dict[str, Any]:
        """Get page information"""
        try:
            url = f"{GRAPH_API_BASE}/{self.page_id}"
            params = {
                "access_token": self.access_token,
                "fields": "id,name,about,fan_count"
            }

            response = requests.get(url, params=params)
            response.raise_for_status()

            page_data = response.json()
            return {
                'success': True,
                'page_id': page_data.get('id'),
                'page_name': page_data.get('name'),
                'about': page_data.get('about', ''),
                'fan_count': page_data.get('fan_count', 0)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def test_authentication(self) -> Dict[str, Any]:
        """Test if access token is valid"""
        try:
            url = f"{GRAPH_API_BASE}/me/accounts"
            params = {"access_token": self.access_token}

            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            pages = data.get("data", [])

            has_page = False
            page_name = None
            for page in pages:
                if page.get("id") == self.page_id:
                    has_page = True
                    page_name = page.get("name")
                    break

            return {
                'success': True,
                'authenticated': True,
                'has_page_access': has_page,
                'pages_accessible': len(pages),
                'page_name': page_name
            }
        except Exception as e:
            return {'success': False, 'authenticated': False, 'error': str(e)}


# Initialize Facebook client
if not FACEBOOK_ACCESS_TOKEN:
    logger.error("FACEBOOK_ACCESS_TOKEN not set in .env file")
    facebook_client = None
else:
    facebook_client = FacebookGraphAPI(FACEBOOK_ACCESS_TOKEN, FACEBOOK_PAGE_ID or "me")


# ── MCP Tool Definitions ──────────────────────────────────────────────────────
# FIX: Changed `input_schema` → `inputSchema` (camelCase) to match the MCP
#      library's types.Tool constructor. snake_case caused a TypeError at startup.

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List all available MCP tools"""
    return [
        types.Tool(
            name="facebook_post",
            description="Post a message to Facebook Page using Graph API",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Text content to post on Facebook"
                    }
                },
                "required": ["message"]
            }
        ),
        types.Tool(
            name="facebook_test_auth",
            description="Test Facebook Graph API authentication",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="facebook_page_info",
            description="Get Facebook Page information",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None
) -> List[types.TextContent]:
    """Handle MCP tool calls"""

    logger.info(f"Facebook tool called: {name}")

    if arguments is None:
        arguments = {}

    if facebook_client is None:
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "error": (
                    "Facebook not configured. "
                    "Please set FACEBOOK_ACCESS_TOKEN and FACEBOOK_PAGE_ID in .env file"
                )
            }, indent=2)
        )]

    try:
        if name == "facebook_post":
            message = arguments.get("message")
            if not message:
                result = {"error": "message is required"}
            else:
                result = facebook_client.post_to_page(message=message)

        elif name == "facebook_test_auth":
            result = facebook_client.test_authentication()

        elif name == "facebook_page_info":
            result = facebook_client.get_page_info()

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


async def main():
    """Run the MCP server using stdio transport"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="facebook-mcp-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())