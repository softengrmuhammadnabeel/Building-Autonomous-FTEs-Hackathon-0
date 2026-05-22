# Odoo Accounting Skill

## Overview
Model Context Protocol server for Odoo accounting and business operations.
Connects to Odoo Community Edition via XML-RPC API for invoicing, customer management, and reporting.

## Triggers
- Invoice creation requests in Needs_Action/
- Customer onboarding from email/WhatsApp requests
- Weekly revenue/expense summaries
- Approved payment actions

## Input
- `AI_Employee_Vault/Needs_Action/` - Invoice creation requests
- `AI_Employee_Vault/Approved/` - Approved accounting actions
- MCP protocol commands from Claude Code

## Output
- Invoices created in Odoo
- Customers added to Odoo CRM
- Revenue/expense reports in Briefings/
- `AI_Employee_Vault/Logs/` - Activity logs

## Usage
```bash
# Start Odoo (Docker)
docker compose up -d

# Test connection
python scripte/odoo_mcp_server.py --health

# Start MCP server
python scripte/odoo_mcp_server.py

# Dry run mode
python scripte/odoo_mcp_server.py --dry-run
```

## Configuration
Set in `.env`:
```
ODOO_URL=http://localhost:8069
ODOO_DB=odoo
ODOO_USERNAME=admin
ODOO_PASSWORD=admin
DRY_RUN=false
ODOO_MAX_ACTIONS_PER_HOUR=50
```

## MCP Methods
- `create_customer(name, email, ...)` — Add new customer
- `search_customers(query)` — Find customers
- `create_invoice(partner_id, lines, ...)` — Create customer invoice
- `search_invoices(partner_id?, state?)` — Find invoices
- `post_invoice(invoice_id)` — Confirm/post invoice
- `create_bill(partner_id, lines, ...)` — Create vendor bill
- `register_payment(invoice_ids, amount)` — Record payment
- `create_product(name, list_price, ...)` — Add product/service
- `search_products(query)` — Find products
- `get_revenue_summary(date_from?, date_to?)` — Revenue report
- `get_expense_summary(date_from?, date_to?)` — Expense report
- `health_check()` — Check Odoo connectivity

## Dependencies
- docker + docker compose (for Odoo)
- xmlrpc.client (Python standard library)
- python-dotenv

## Setup
1. Install Docker Desktop for Windows
2. Run `docker compose up -d` to start Odoo Community
3. Access Odoo at http://localhost:8069
4. Complete initial Odoo setup (create database, install Accounting app)
5. Set credentials in `.env`
6. Test: `python scripte/odoo_mcp_server.py --health`

## Architecture
```
Claude Code → Odoo MCP Server → XML-RPC → Odoo Community (Docker)
                                              ↓
                                         PostgreSQL
```

## HITL Workflow
1. AI creates accounting request in Needs_Action/
2. Approval manager creates request in Pending_Approval/
3. Human reviews and moves to Approved/
4. Odoo MCP Server executes the action
5. Result logged to Logs/
