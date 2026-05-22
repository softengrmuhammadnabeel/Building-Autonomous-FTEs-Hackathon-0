# Odoo Community Edition — Local Setup

> Gold Tier AI Employee — Accounting System

---

## 📁 Folder Contents

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Docker services (Odoo + PostgreSQL) |
| `odoo.conf` | Odoo server configuration |
| `.env.odoo` | Environment variables for Docker |
| `odoo-start.bat` | Windows management script |
| `README.md` | This file |

---

## 🚀 Quick Start

### Start Odoo

```cmd
odoo-start.bat
```

Or manually:

```cmd
docker compose up -d
```

### Access

- **Web UI:** http://localhost:8069
- **Database:** localhost:5432 (user: `odoo`, pass: `odoo`)
- **Admin:** `admin` / `admin`

### First-Time Setup

1. Open http://localhost:8069
2. Create a new database (name it `odoo`)
3. Set admin password to `admin` (match `.env` settings)
4. Install **Accounting** and **Invoicing** apps

---

## 🔧 Management Commands

| Command | Action |
|---------|--------|
| `odoo-start.bat start` | Start services |
| `odoo-start.bat stop` | Stop services |
| `odoo-start.bat restart` | Restart services |
| `odoo-start.bat logs` | View logs |
| `odoo-start.bat status` | Check service status |
| `odoo-start.bat health` | Run health check |
| `odoo-start.bat clean` | Delete all data (⚠️ destructive) |

---

## 🔗 Integration with AI Employee

The Odoo MCP Server (`scripte/odoo_mcp_server.py`) connects to this Odoo instance via XML-RPC.

**Required `.env` entries** (in project root):

```env
ODOO_URL=http://localhost:8069
ODOO_DB=odoo
ODOO_USERNAME=admin
ODOO_PASSWORD=admin
```

**Test connection:**

```cmd
cd ..
python scripte/odoo_mcp_server.py --health
```

---

## 🛡️ Security

- Default password is `admin` — **change for production**
- Database is isolated in Docker volumes
- No external ports exposed beyond localhost
- Credentials stored in `.env` (never committed)
