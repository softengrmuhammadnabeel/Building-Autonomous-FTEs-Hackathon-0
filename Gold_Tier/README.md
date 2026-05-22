# GOLD TIER | AI EMPLOYEE

**4 Integrations | MCP Architecture | Fully Autonomous**

---

## 1.0 What's New in Gold

| Feature | Status |
|---------|--------|
| Facebook Auto-Poster | ✅ Live |
| Odoo Accounting (XML-RPC) | ✅ Live |
| Ralph Wiggum Loop (24/7 Monitor) | ✅ Live |
| Weekly CEO Briefings | ✅ Live |

---

## 2.0 Quick Setup (3 Steps)

```bash
cd script
pip install -r requirements.txt
python orchestrator.py --vault "../AI_Employee_Vault"
```

> **Note:** All folders auto-create on first run.

---

## 3.0 Integration Status

| Service | Type | Script | Skill |
|---------|------|--------|-------|
| Gmail | Watcher | `script/gmail_watcher.py` | `.qwen/skills/gmail-watcher/` |
| LinkedIn | MCP | `script/linkedin_mcp_server.py` | `.qwen/skills/linkedin-auto-poster/` |
| Facebook | MCP | `script/facebook_mcp_server.py` | `.qwen/skills/facebook-auto-poster/` |
| Odoo | MCP | `script/odoo_mcp_server.py` | `.qwen/skills/odoo-accounting/` |

---

## 4.0 Folder Structure

```
GOLD_TIER/
│
├── .qwen/                          # Qwen Code configuration
│  
├── gmail_credentials/              # Gmail authentication
│   ├── credentials.json
│   └── gmail_token.json
│
├── AI_Employee_Vault/              # Obsidian knowledge base
│   ├── Inbox/
│   ├── Needs_Action/
│   ├── Pending_Approval/
│   ├── Approved/
│   ├── Done/
│   ├── Logs/
│   ├── Reports/
│   ├── Briefings/
│   ├── Accounting/
│   ├── Invoices/
│   ├── Dashboard.md
│   ├── Business_Goals.md
│   └── Company_Handbook.md
│
├── odoo/                           # Docker setup
│   └── docker-compose.yml
│
├── script/                         # All Python scripts
│
├── .env                            # Environment variables
│
├── Personal AI Employee Hackathon 0_Build...
├── QWEN.md
└── README.md
```

---

## 5.0 Core Commands

Run all from `script` folder:

```bash
# Orchestrator (RECOMMENDED - handles all services)
python orchestrator.py --vault "../AI_Employee_Vault"

# Gmail only
python gmail_watcher.py --auto

# LinkedIn only
python linkedin_mcp_server.py

# Facebook MCP
python facebook_mcp_server.py --vault "../AI_Employee_Vault"

# Odoo MCP
python odoo_mcp_server.py

# Ralph Loop (24/7 monitoring)
python ralph_loop.py --mode hybrid

# Weekly audit
python weekly_audit.py


```

---

## 6.0 Odoo MCP Server Commands

| Command | What It Does |
|---------|---------------|
| `--direct "Name" Amount "Product"` | Creates + Posts invoice in Odoo (auto-creates customer if not exists) |
| `--quick "Name" Amount "Product"` | Creates file in Needs_Action folder (orchestrator processes later) |

### Usage Examples

```bash
# Direct: Create and post invoice immediately
python odoo_mcp_server.py --direct "ABC Corp" 1500 "Consulting"

# Quick: Create file for orchestrator
python odoo_mcp_server.py --quick "ABC Corp" 1500 "Consulting"
```

### What Happens

| Command | Action |
|---------|--------|
| `--direct` | Customer auto-created (if needed) → Invoice created → Invoice posted → Accounting records saved |
| `--quick` | File created in Needs_Action folder → Orchestrator processes later |

### Additional Odoo Commands

```bash
# View all invoices
python odoo_mcp_server.py --accounting

# Check Odoo connection
python odoo_mcp_server.py --health

# Start server mode (for orchestrator)
python odoo_mcp_server.py
```

### Odoo File Locations

| Mode | Location |
|------|----------|
| `--direct` | `AI_Employee_Vault/Accounting/` |
| `--quick` | `AI_Employee_Vault/Needs_Action/` |

---

## 7.0 Environment Variables (.env)

```env
# Gmail
GMAIL_CREDENTIALS_PATH=gmail_credentials/credentials.json

# LinkedIn
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_password

# Facebook
FACEBOOK_APP_ID=your_id
FACEBOOK_APP_SECRET=your_secret
FACEBOOK_ACCESS_TOKEN=your_token
FACEBOOK_PAGE_ID=your_page

# Odoo
ODOO_URL=http://localhost:8069
ODOO_DB=odoo
ODOO_USERNAME=admin
ODOO_PASSWORD=admin

# Rate Limits
MAX_ACTIONS_PER_HOUR=50
DRY_RUN=false
```

---

## 8.0 Setup Guides

### Gmail Setup
```bash
cd script
setup_gmail.bat
```

### LinkedIn Setup
```bash
cd script
setup_linkedin.bat
```

### Facebook Setup
1. Create Facebook App at developers.facebook.com
2. Add `manage_pages` permission
3. Add credentials to `.env`
4. Test: `python facebook_mcp_server.py --test`

### Odoo Setup (Docker)
```bash
cd odoo
docker compose up -d
```
Access: `http://localhost:8069` (admin/admin)

---

## 9.0 Ralph Wiggum Loop

**Never-dying monitor** that generates daily reports:

| Report | Location |
|--------|----------|
| CEO Daily Briefing | `AI_Employee_Vault/Reports/CEO_DAILY_BRIEFING_*.md` |
| CEO Weekly Briefing | `AI_Employee_Vault/Briefings/CEO_WEEKLY_BRIEFING_*.md` |
| Email Report | `AI_Employee_Vault/Reports/RALPH_EMAIL_REPORT_*.md` |
| Social Report | `AI_Employee_Vault/Reports/RALPH_SOCIAL_REPORT_*.md` |

```bash
cd script
python ralph_loop.py --mode hybrid
```

---

## 10.0 MCP Methods

### Odoo MCP

| Method | What it does |
|--------|--------------|
| `create_customer` | Add customer |
| `create_invoice` | Generate invoice |
| `post_invoice` | Confirm invoice |
| `register_payment` | Record payment |
| `get_revenue_summary` | Revenue report |

### Facebook MCP

| Method | What it does |
|--------|--------------|
| `create_post` | Publish to page |
| `schedule_post` | Schedule post |
| `get_page_insights` | Analytics |

---

## 11.0 Complete Workflow

| Step | Action | Command |
|------|--------|---------|
| 1 | Setup Gmail | `setup_gmail.bat` |
| 2 | Setup LinkedIn | `setup_linkedin.bat` |
| 3 | Start Odoo | `cd odoo && docker compose up -d` |
| 4 | Run orchestrator | `python orchestrator.py --vault "../AI_Employee_Vault"` |
| 5 | Monitor with Ralph | `python ralph_loop.py --mode hybrid` |

---

## 12.0 Important Notes

| Issue | Truth |
|-------|-------|
| Empty folders after clone | Normal - auto-create on run |
| MCP JSON-RPC errors | Expected - use orchestrator |
| Event loop closed | Press Ctrl+C once only |

---

## 13.0 Version History

| Tier | Status | Integrations |
|------|--------|--------------|
| Bronze | ✅ | File watcher |
| Silver | ✅ | Gmail + LinkedIn |
| Gold | ✅ | + Facebook + Odoo |

---

## 14.0 Support

- Logs: `AI_Employee_Vault/Logs/`
- Errors: Check `ralph_loop_*.log`
- Help: `python script.py --help`

---

**End of Documentation**