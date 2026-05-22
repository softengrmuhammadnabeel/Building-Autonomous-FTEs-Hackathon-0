"""
Odoo MCP Server - Official MCP SDK Version

Model Context Protocol server for Odoo accounting and business operations.
Uses official MCP Python SDK.

Part of the Gold Tier AI Employee system.
"""

import asyncio
import sys
import os
import json
import logging
import signal
import re
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Union
import xmlrpc.client

from dotenv import load_dotenv
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Load environment variables
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / '.env')

# Setup logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger('OdooMCP')

# Create MCP Server instance
server = Server("odoo-mcp-server")

# Vault paths
VAULT_PATH = Path(os.getenv("AI_EMPLOYEE_VAULT", str(PROJECT_ROOT / "AI_Employee_Vault")))
NEEDS_ACTION = VAULT_PATH / "Needs_Action"
APPROVED = VAULT_PATH / "Approved"
ACCOUNTING = VAULT_PATH / "Accounting"


class AccountingManager:
    """Manages accounting records in vault"""
    
    @staticmethod
    def save_invoice_record(invoice_data: Dict[str, Any]) -> bool:
        """Save invoice record to Accounting folder"""
        try:
            ACCOUNTING.mkdir(parents=True, exist_ok=True)
            
            invoice_id = invoice_data.get('invoice_id')
            if not invoice_id:
                logger.warning("No invoice_id found, skipping save")
                return False
            
            invoice_file = ACCOUNTING / f"invoice_{invoice_id}.json"
            
            if 'saved_at' not in invoice_data:
                invoice_data['saved_at'] = datetime.now().isoformat()
            
            with open(invoice_file, 'w', encoding='utf-8') as f:
                json.dump(invoice_data, f, indent=2, default=str)
            
            logger.info(f"Invoice record saved: {invoice_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save invoice record: {e}")
            return False
    
    @staticmethod
    def save_transaction_record(
        invoice_id: int,
        customer_name: str,
        amount: float,
        customer_id: Optional[int] = None,
        transaction_type: str = "invoice_created"
    ) -> bool:
        """Save transaction record to Accounting folder"""
        try:
            ACCOUNTING.mkdir(parents=True, exist_ok=True)
            
            transaction_file = ACCOUNTING / f"transaction_{invoice_id}.json"
            
            transaction_data = {
                "transaction_id": f"TXN-{invoice_id}",
                "invoice_id": invoice_id,
                "customer_name": customer_name,
                "customer_id": customer_id,
                "amount": amount,
                "type": transaction_type,
                "date": date.today().isoformat(),
                "timestamp": datetime.now().isoformat()
            }
            
            with open(transaction_file, 'w', encoding='utf-8') as f:
                json.dump(transaction_data, f, indent=2, default=str)
            
            logger.info(f"Transaction record saved: {transaction_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save transaction record: {e}")
            return False
    
    @staticmethod
    def update_invoice_status(invoice_id: int, status: str) -> bool:
        """Update invoice status in existing record"""
        try:
            invoice_file = ACCOUNTING / f"invoice_{invoice_id}.json"
            
            if not invoice_file.exists():
                logger.warning(f"Invoice file not found: {invoice_file}")
                return False
            
            with open(invoice_file, 'r', encoding='utf-8') as f:
                invoice_data = json.load(f)
            
            invoice_data['status'] = status
            invoice_data['posted_at'] = datetime.now().isoformat()
            
            with open(invoice_file, 'w', encoding='utf-8') as f:
                json.dump(invoice_data, f, indent=2, default=str)
            
            logger.info(f"Invoice status updated: {invoice_id} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update invoice status: {e}")
            return False
    
    @staticmethod
    def get_all_invoices() -> List[Dict[str, Any]]:
        """Get all invoice records from Accounting folder"""
        try:
            invoices = []
            for file in ACCOUNTING.glob("invoice_*.json"):
                with open(file, 'r', encoding='utf-8') as f:
                    invoices.append(json.load(f))
            return sorted(invoices, key=lambda x: x.get('invoice_id', 0))
        except Exception as e:
            logger.error(f"Failed to get invoices: {e}")
            return []
    
    @staticmethod
    def get_revenue_summary() -> Dict[str, Any]:
        """Get revenue summary from all posted invoices"""
        try:
            invoices = AccountingManager.get_all_invoices()
            posted_invoices = [inv for inv in invoices if inv.get('status') == 'posted']
            
            total_revenue = sum(inv.get('amount', 0) for inv in posted_invoices)
            
            return {
                'total_invoices': len(invoices),
                'posted_invoices': len(posted_invoices),
                'total_revenue': total_revenue,
                'average_invoice': total_revenue / len(posted_invoices) if posted_invoices else 0
            }
        except Exception as e:
            logger.error(f"Failed to get revenue summary: {e}")
            return {'error': str(e)}


class OdooClient:
    """Odoo XML-RPC client wrapper"""

    def __init__(self):
        self.url: str = os.getenv("ODOO_URL", "http://localhost:8069")
        self.db: str = os.getenv("ODOO_DB", "odoo")
        self.username: str = os.getenv("ODOO_USERNAME", "admin")
        self.password: str = os.getenv("ODOO_PASSWORD", "admin")
        self.dry_run: bool = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")

        self.uid: Optional[int] = None
        self.common: Optional[Any] = None
        self.models: Optional[Any] = None
        self.connected: bool = False

        self._authenticate()

    def _authenticate(self) -> bool:
        """Authenticate with Odoo via XML-RPC"""
        try:
            url_common = f"{self.url}/xmlrpc/2/common"
            self.common = xmlrpc.client.ServerProxy(url_common, allow_none=True)

            auth_result = self.common.authenticate(self.db, self.username, self.password, {})

            if isinstance(auth_result, int):
                self.uid = auth_result
            else:
                self.uid = None

            if not self.uid:
                logger.error(f"Odoo authentication failed for user: {self.username}")
                return False

            url_models = f"{self.url}/xmlrpc/2/object"
            self.models = xmlrpc.client.ServerProxy(url_models, allow_none=True)

            self.connected = True
            logger.info(f"Odoo authenticated as user ID: {self.uid}")
            return True

        except Exception as e:
            logger.error(f"Odoo authentication failed: {e}")
            return False

    def execute(self, model: str, method: str, *args, **kwargs):
        """Execute method on Odoo model"""
        if not self.connected:
            self._authenticate()

        if self.models is None:
            raise ConnectionError("Not connected to Odoo")

        return self.models.execute_kw(self.db, self.uid, self.password, model, method, args, kwargs)

    def search_customer_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Search for a customer by name"""
        try:
            domain = [('name', 'ilike', name)]
            customer_ids = self.execute('res.partner', 'search', domain, limit=1)

            if not customer_ids:
                return None

            customers = self.execute('res.partner', 'read', customer_ids, ['id', 'name', 'email'])
            return customers[0] if customers else None
        except Exception as e:
            logger.error(f"Customer search failed: {e}")
            return None

    def create_customer(self, name: str, email: str = "", phone: str = "", city: str = "") -> Dict[str, Any]:
        """Create a new customer in Odoo"""
        if self.dry_run:
            return {'status': 'dry_run', 'customer_id': None}

        try:
            # Generate email if not provided
            if not email:
                email = f"{name.lower().replace(' ', '.')}@example.com"
            
            vals: Dict[str, Any] = {
                'name': name,
                'email': email,
                'customer_rank': 1,
            }
            if phone:
                vals['phone'] = phone
            if city:
                vals['city'] = city

            customer_id = self.execute('res.partner', 'create', vals)
            logger.info(f"Customer created: {name} (ID: {customer_id})")

            return {
                'success': True,
                'customer_id': customer_id,
                'name': name,
                'email': email
            }
        except Exception as e:
            logger.error(f"Failed to create customer: {e}")
            return {'success': False, 'error': str(e)}

    def get_or_create_customer(self, name: str, email: str = "", phone: str = "", city: str = "") -> Dict[str, Any]:
        """Get existing customer or create new one"""
        # First search for customer
        customer = self.search_customer_by_name(name)
        
        if customer:
            logger.info(f"Customer found: {name} (ID: {customer['id']})")
            return {
                'success': True,
                'customer_id': customer['id'],
                'name': customer['name'],
                'email': customer.get('email', ''),
                'existing': True
            }
        else:
            # Create new customer
            logger.info(f"Customer not found, creating: {name}")
            result = self.create_customer(name, email, phone, city)
            if result.get('success'):
                result['existing'] = False
            return result

    def create_and_post_invoice(self, partner_id: int, lines: List[Dict[str, Any]], invoice_date: Optional[str] = None) -> Dict[str, Any]:
        """Create and immediately post an invoice in Odoo"""
        if self.dry_run:
            return {'status': 'dry_run', 'invoice_id': None}

        try:
            # Step 1: Create invoice
            vals: Dict[str, Any] = {
                'partner_id': partner_id,
                'move_type': 'out_invoice',
                'invoice_date': invoice_date or date.today().isoformat(),
                'invoice_line_ids': [
                    (0, 0, {
                        'name': line.get('name', 'Service'),
                        'quantity': line.get('quantity', 1),
                        'price_unit': line.get('price_unit', 0),
                    })
                    for line in lines
                ],
            }

            invoice_id = self.execute('account.move', 'create', vals)
            logger.info(f"Invoice created: ID {invoice_id}")
            
            # Step 2: Post the invoice immediately
            self.execute('account.move', 'action_post', [invoice_id])
            logger.info(f"Invoice {invoice_id} posted successfully")
            
            return {'success': True, 'invoice_id': invoice_id, 'status': 'posted'}
        except Exception as e:
            logger.error(f"Failed to create/post invoice: {e}")
            return {'success': False, 'error': str(e)}

    def create_invoice_for_customer(self, customer_name: str, amount: float, product_name: str = "Service", 
                                     customer_email: str = "", customer_phone: str = "") -> Dict[str, Any]:
        """Create and post invoice for a customer (auto-creates customer if not exists)"""
        
        # Get or create customer
        customer_result = self.get_or_create_customer(customer_name, customer_email, customer_phone)
        
        if not customer_result.get('success'):
            return {'success': False, 'error': f'Failed to get/create customer: {customer_result.get("error")}'}
        
        customer_id = customer_result['customer_id']
        customer_created = not customer_result.get('existing', True)
        
        # Create invoice lines
        lines = [{'name': product_name, 'quantity': 1, 'price_unit': amount}]
        result = self.create_and_post_invoice(customer_id, lines)

        if result.get('success'):
            invoice_data = {
                'invoice_id': result['invoice_id'],
                'customer_name': customer_name,
                'customer_id': customer_id,
                'amount': amount,
                'product_name': product_name,
                'date': date.today().isoformat(),
                'status': 'posted',
                'source': 'odoo_mcp_server',
                'saved_at': datetime.now().isoformat(),
                'posted_at': datetime.now().isoformat(),
                'customer_created': customer_created
            }
            
            # Save accounting records
            AccountingManager.save_invoice_record(invoice_data)
            AccountingManager.save_transaction_record(
                invoice_id=result['invoice_id'],
                customer_name=customer_name,
                amount=amount,
                customer_id=customer_id,
                transaction_type='invoice_created'
            )
            
            return {
                'success': True,
                'invoice_id': result['invoice_id'],
                'customer': customer_name,
                'customer_id': customer_id,
                'amount': amount,
                'product_name': product_name,
                'status': 'posted',
                'customer_created': customer_created
            }
        return result

    def post_invoice(self, invoice_id: int) -> Dict[str, Any]:
        """Post/confirm an invoice"""
        if self.dry_run:
            return {'status': 'dry_run'}
        try:
            self.execute('account.move', 'action_post', [invoice_id])
            
            # Update status in accounting records
            AccountingManager.update_invoice_status(invoice_id, 'posted')
            
            return {'success': True, 'invoice_id': invoice_id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check Odoo connectivity"""
        try:
            url_common = f"{self.url}/xmlrpc/2/common"
            common = xmlrpc.client.ServerProxy(url_common, allow_none=True)
            version = common.version()
            return {'status': 'healthy', 'odoo_version': version, 'connected': self.connected, 'url': self.url}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}


# Initialize Odoo client
odoo = OdooClient()


def create_needs_action_file(
    customer_name: str,
    amount: float,
    product_name: str = "Service",
    customer_email: str = "",
    customer_phone: str = "",
    description: str = ""
) -> Path:
    """Create a Needs_Action file for orchestrator to process"""
    
    NEEDS_ACTION.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', customer_name)[:30]
    filename = NEEDS_ACTION / f"INVOICE_{safe_name}_{timestamp}.md"
    
    content = f"""---
type: invoice_creation
platform: odoo
customer_name: "{customer_name}"
amount: {amount:.2f}
product_name: "{product_name}"
auto_post: false
"""

    if customer_email:
        content += f'customer_email: "{customer_email}"\n'
    if customer_phone:
        content += f'customer_phone: "{customer_phone}"\n'

    content += f"""
---

# Invoice Creation Request

## Customer Information
- Name: {customer_name}
"""

    if customer_email:
        content += f"- Email: {customer_email}\n"
    if customer_phone:
        content += f"- Phone: {customer_phone}\n"

    content += f"""
## Invoice Details
- Amount: ${amount:,.2f}
- Product/Service: {product_name}
- Status: Pending Approval

"""

    if description:
        content += f"""
## Description
{description}

"""

    content += """
---
*Generated by Odoo MCP Server - CLI Mode*
*Move to Approved/ folder when ready to create invoice*
"""
    
    filename.write_text(content, encoding='utf-8')
    return filename


# MCP Tool Definitions
@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List all available MCP tools"""
    return [
        types.Tool(
            name="odoo_health_check",
            description="Check if Odoo server is reachable and healthy",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        types.Tool(
            name="odoo_create_customer",
            description="Create a new customer in Odoo",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Customer full name"},
                    "email": {"type": "string", "description": "Customer email address"},
                    "phone": {"type": "string", "description": "Customer phone number"},
                    "city": {"type": "string", "description": "Customer city"}
                },
                "required": ["name"]
            }
        ),
        types.Tool(
            name="odoo_create_invoice_for_customer",
            description="Create and post an invoice (auto-creates customer if not exists)",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Name of the customer"},
                    "amount": {"type": "number", "description": "Invoice amount"},
                    "product_name": {"type": "string", "description": "Product or service name"},
                    "customer_email": {"type": "string", "description": "Customer email (optional)"},
                    "customer_phone": {"type": "string", "description": "Customer phone (optional)"}
                },
                "required": ["customer_name", "amount"]
            }
        ),
        types.Tool(
            name="odoo_post_invoice",
            description="Post/confirm a draft invoice",
            inputSchema={
                "type": "object",
                "properties": {"invoice_id": {"type": "integer", "description": "Invoice ID"}},
                "required": ["invoice_id"]
            }
        ),
        types.Tool(
            name="odoo_get_accounting_summary",
            description="Get accounting summary from vault",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        types.Tool(
            name="odoo_list_invoices",
            description="List all invoices from accounting records",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> List[types.TextContent]:
    """Handle MCP tool calls"""
    if arguments is None:
        arguments = {}
    result: Dict[str, Any] = {}

    try:
        if name == "odoo_health_check":
            result = odoo.health_check()
        elif name == "odoo_create_customer":
            customer_name = arguments.get("name")
            if not customer_name:
                result = {"error": "name is required"}
            else:
                result = odoo.create_customer(
                    customer_name, 
                    arguments.get("email", ""),
                    str(arguments.get("phone", "")), 
                    str(arguments.get("city", ""))
                )
        elif name == "odoo_create_invoice_for_customer":
            customer_name = arguments.get("customer_name")
            amount_raw = arguments.get("amount")
            if not customer_name or amount_raw is None:
                result = {"error": "customer_name and amount are required"}
            else:
                result = odoo.create_invoice_for_customer(
                    customer_name, 
                    float(amount_raw), 
                    str(arguments.get("product_name", "Service")),
                    str(arguments.get("customer_email", "")),
                    str(arguments.get("customer_phone", ""))
                )
        elif name == "odoo_post_invoice":
            invoice_id = arguments.get("invoice_id")
            if invoice_id is None:
                result = {"error": "invoice_id is required"}
            else:
                result = odoo.post_invoice(int(invoice_id))
        elif name == "odoo_get_accounting_summary":
            result = AccountingManager.get_revenue_summary()
        elif name == "odoo_list_invoices":
            result = {
                'invoices': AccountingManager.get_all_invoices(),
                'total': len(AccountingManager.get_all_invoices())
            }
        else:
            result = {"error": f"Unknown tool: {name}"}
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


# CLI Mode
def run_cli_mode():
    """Run CLI mode"""
    
    if len(sys.argv) < 2:
        print("\nODOO INVOICE CREATOR (CLI Mode)")
        print("=" * 50)
        print("\nUsage:")
        print("  python odoo_mcp_server.py --quick \"Customer Name\" Amount")
        print("  python odoo_mcp_server.py --direct \"Customer Name\" Amount")
        print("  python odoo_mcp_server.py --accounting")
        print("  python odoo_mcp_server.py --help")
        print("\nExamples:")
        print("  python odoo_mcp_server.py --direct \"KBC Cabin\" 2500 \"Textile\"")
        print("\nNote: Customer will be auto-created if not exists")
        return
    
    if sys.argv[1] in ["--help", "-h"]:
        print("\nODOO INVOICE CREATOR - Quick Guide")
        print("=" * 50)
        print("\nCommands:")
        print("  --quick   : Creates file in Needs_Action folder")
        print("  --direct  : Creates + Posts invoice in Odoo (auto-creates customer)")
        print("  --accounting: Shows all invoices from vault")
        print("  --health  : Check Odoo connection")
        print("\nExamples:")
        print("  python odoo_mcp_server.py --direct \"KBC Cabin\" 2500 \"Textile\"")
        print("  python odoo_mcp_server.py --direct \"New Customer\" 5000 \"Service\"")
        print("\nNote: Customer auto-created if not exists in Odoo")
        return
    
    if sys.argv[1] in ["--accounting"]:
        print("\nACCOUNTING RECORDS")
        print("=" * 50)
        
        invoices = AccountingManager.get_all_invoices()
        
        if not invoices:
            print("No invoices found in accounting records.")
        else:
            print(f"Total Invoices: {len(invoices)}")
            print("-" * 50)
            
            total_amount = 0
            for inv in invoices:
                amount = inv.get('amount', 0)
                total_amount += amount
                customer_created = " (auto-created)" if inv.get('customer_created') else ""
                print(f"  #{inv.get('invoice_id')}: {inv.get('customer_name')} - ${amount:,.2f} ({inv.get('status', 'unknown')}){customer_created}")
            
            print("-" * 50)
            print(f"Total Revenue: ${total_amount:,.2f}")
        
        print("=" * 50)
        return
    
    if sys.argv[1] in ["--quick", "-q"]:
        if len(sys.argv) < 4:
            print("\nError: Customer name and amount required!")
            return
        
        customer_name = sys.argv[2]
        
        try:
            amount = float(sys.argv[3])
        except ValueError:
            print(f"\nError: '{sys.argv[3]}' is not a valid amount!")
            return
        
        product_name = sys.argv[4] if len(sys.argv) > 4 else "Service"
        
        print("\n" + "=" * 50)
        print("CREATING INVOICE REQUEST")
        print("=" * 50)
        print(f"  Customer:    {customer_name}")
        print(f"  Amount:      ${amount:,.2f}")
        print(f"  Product:     {product_name}")
        print("-" * 50)
        
        try:
            filename = create_needs_action_file(
                customer_name=customer_name,
                amount=amount,
                product_name=product_name
            )
            
            print("\nFILE CREATED SUCCESSFULLY!")
            print("=" * 50)
            print(f"  File:        {filename.name}")
            print(f"  Location:    {NEEDS_ACTION}")
            print("-" * 50)
            
            print("\nNEXT STEPS:")
            print("  1. Orchestrator will detect the file")
            print("  2. Move to Approved/ folder when ready")
            print("  3. Invoice will be created in Odoo automatically")
            print(f"\n  Full path: {filename}")
            print("\n" + "=" * 50)
            
        except Exception as e:
            print(f"\nError creating file: {e}")
            print("=" * 50)
        
        return
    
    if sys.argv[1] in ["--direct", "-d"]:
        if len(sys.argv) < 4:
            print("\nError: Customer name and amount required!")
            print("Usage: python odoo_mcp_server.py --direct \"Customer Name\" Amount [Product Name]")
            return
        
        customer_name = sys.argv[2]
        
        try:
            amount = float(sys.argv[3])
        except ValueError:
            print(f"\nError: '{sys.argv[3]}' is not a valid amount!")
            return
        
        product_name = sys.argv[4] if len(sys.argv) > 4 else "Service"
        
        print("\n" + "=" * 50)
        print("CREATING AND POSTING INVOICE IN ODOO")
        print("=" * 50)
        print(f"  Customer:    {customer_name}")
        print(f"  Amount:      ${amount:,.2f}")
        print(f"  Product:     {product_name}")
        print("-" * 50)
        
        # Create invoice (auto-creates customer if not exists)
        result = odoo.create_invoice_for_customer(customer_name, amount, product_name)
        
        if result.get('success'):
            print("\nINVOICE CREATED AND POSTED IN ODOO!")
            print("=" * 50)
            print(f"  Invoice #:   {result['invoice_id']}")
            print(f"  Customer:    {result['customer']}")
            print(f"  Amount:      ${result['amount']:,.2f}")
            print(f"  Status:      POSTED")
            
            if result.get('customer_created'):
                print(f"  Note:        Customer was auto-created in Odoo")
            
            print("-" * 50)
            
            print(f"\nAccounting records saved in:")
            print(f"  - {ACCOUNTING / f'invoice_{result["invoice_id"]}.json'}")
            print(f"  - {ACCOUNTING / f'transaction_{result["invoice_id"]}.json'}")
            
            print("\nInvoice is already confirmed/posted in Odoo.")
            print("=" * 50)
        else:
            print(f"\nFAILED TO CREATE INVOICE!")
            print("=" * 50)
            print(f"  Error: {result.get('error')}")
            print("=" * 50)
        return
    
    if sys.argv[1] in ["--health"]:
        print("\nODOO HEALTH CHECK")
        print("=" * 50)
        result = odoo.health_check()
        if result.get('status') == 'healthy':
            print("Status: HEALTHY")
            print(f"  URL:       {result.get('url')}")
            print(f"  Connected: {result.get('connected')}")
        else:
            print("Status: UNHEALTHY")
            print(f"  Error: {result.get('error')}")
        print("=" * 50)
        return
    
    print(f"\nUnknown option: {sys.argv[1]}")
    print("Run 'python odoo_mcp_server.py --help' for usage")


async def run_mcp_server():
    """Run MCP server with proper signal handling"""
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream): # type: ignore
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="odoo-mcp-server",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\nServer error: {e}", file=sys.stderr)
        sys.exit(1)


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\nShutting down Odoo MCP Server...", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    
    if len(sys.argv) > 1:
        run_cli_mode()
    else:
        print("Starting Odoo MCP Server...", file=sys.stderr)
        print("Waiting for orchestrator connection...", file=sys.stderr)
        print("Press Ctrl+C to stop the server\n", file=sys.stderr)
        
        try:
            asyncio.run(run_mcp_server())
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"\nFatal error: {e}", file=sys.stderr)
            sys.exit(1)