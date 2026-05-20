# AI Employee - Silver Tier

**Silver Tier** adds external service integration to the Bronze Tier foundation. This release introduces Gmail monitoring and LinkedIn automation with a human-in-the-loop approval workflow. All actions require explicit approval before execution, ensuring safe autonomous operation.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AI Employee System                     │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Gmail Watcher          LinkedIn Poster                  │
│  ┌──────────────┐       ┌──────────────────┐            │
│  │ Monitor Gmail│       │ Post to LinkedIn │            │
│  │ Create files │       │ Requires approval│            │
│  └──────┬───────┘       └────────┬─────────┘            │
│         │                        │                       │
│         ▼                        ▼                       │
│  ┌──────────────────────────────────────┐               │
│  │        Needs_Action Folder            │               │
│  │  EMAIL_*.md  │  POST_*.md            │               │
│  └──────────────┴──────────┬───────────┘               │
│                             │                            │
│                             ▼                            │
│                  ┌────────────────────┐                 │
│                  │  Orchestrator      │                 │
│                  │  (Qwen Code)       │                 │
│                  └────────┬───────────┘                 │
│                           │                              │
│              ┌────────────┴────────────┐                │
│              ▼                         ▼                 │
│  ┌──────────────────┐      ┌───────────────────┐       │
│  │ Pending_Approval │      │      Done          │       │
│  │ (HITL Pattern)   │      │  (Completed)       │       │
│  └────────┬─────────┘      └───────────────────┘       │
│           │                                             │
│           ▼ (User approves)                             │
│  ┌──────────────────┐                                   │
│  │     Approved      │                                   │
│  │  → Post to LI     │                                   │
│  └──────────────────┘                                   │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Architecture Notes

**Qwen Code as the Brain:**
- The orchestrator is configured to use Qwen Code (`ai_agent = 'qwen'`)
- All AI functionality is implemented as Agent Skills
- Skills are defined in `.qwen/skills/` directory
- The orchestrator processes files using the configured AI agent

**Human-in-the-Loop:**
- LinkedIn posts require approval before publishing
- Approval files created in `Pending_Approval/`
- User moves to `Approved/` to authorize
- Orchestrator executes after approval

**Security:**
- Credentials never committed to version control
- `.env` file contains sensitive data
- OAuth tokens auto-managed and refreshable
- `DRY_RUN` mode for safe testing

---

## Silver Tier Checklist

| Feature | Status |
|---------|--------|
| All Bronze requirements | ✅ |
| Two or more Watcher scripts (Gmail + LinkedIn) | ✅ |
| Automatically Post on LinkedIn | ✅ |
| Qwen reasoning loop with Plan.md files | ✅ |
| One working MCP server | ✅ |
| Human-in-the-loop approval workflow | ✅ |
| Basic scheduling via Task Scheduler | ✅ |
| All AI functionality as Agent Skills | ✅ |

---

## File Structure

```
SILVER_TIER/
│
├── .qwen/
│   └── skills/
│
├── gmail_credentials/
│
├── AI_Employee_Vault/
│   ├── .obsidian/
│   ├── Accounting/
│   ├── Approved/
│   ├── Briefings/
│   ├── Done/
│   ├── Drop/
│   ├── Failed/
│   ├── Inbox/
│   ├── Invoices/
│   ├── Logs/
│   ├── Needs_Action/
│   ├── Pending_Approval/
│   ├── Plans/
│   ├── Processing/
│   ├── Rejected/
│   ├── Business_Goals.md
│   ├── Company_Handbook.md
│   └── Dashboard.md
│
├── script/
│
├── .env
│
├── Personal AI Employee Hackathon 0_Build...
├── QWEN.md
└── README.md
```

---

## Quick Start

### 1. Install Dependencies
```bash
cd script
pip install -r requirements.txt
playwright install chromium
```

### 2. Setup Gmail
```bash
setup_gmail.bat
```

### 3. Setup LinkedIn
Edit `.env` file:
```env
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_password
DRY_RUN=true
```

### 4. Run Orchestrator
```bash
python orchestrator.py --vault "../AI_Employee_Vault" --watch
```

---

## Components

| Component | Purpose |
|-----------|---------|
| `base_watcher.py` | Base class for all watchers |
| `gmail_watcher.py` | Gmail monitoring |
| `linkedin_poster.py` | LinkedIn posting automation |
| `orchestrator.py` | Main coordinator |
| `approval_manager.py` | HITL approval workflow |

---

## Commands

Run from `script` directory:

```bash
# Orchestrator (both services)
python orchestrator.py --vault "../AI_Employee_Vault" --watch

# Gmail only
python gmail_watcher.py --vault "../AI_Employee_Vault" --credentials ../gmail_credentials/credentials.json

# LinkedIn only
python linkedin_poster.py --vault "../AI_Employee_Vault"
```

---

## Test Workflow

### Test Gmail
```bash
python gmail_watcher.py
```
Check: `AI_Employee_Vault/Needs_Action/EMAIL_*.md`

### Test LinkedIn
1. Create `AI_Employee_Vault/Needs_Action/POST_test.md`
2. Run `python orchestrator.py --vault "../AI_Employee_Vault" --watch`
3. Move `Pending_Approval/LINKEDIN_*.md` → `Approved/`

---

## Directory Path Reference

| Location | Path |
|----------|------|
| Root Directory | `S:\Silver_Tier\` |
| Scripts | `S:\Silver_Tier\script\` |
| Vault | `S:\Silver_Tier\AI_Employee_Vault\` |
| Gmail Credentials | `S:\Silver_Tier\gmail_credentials\` |
| Environment | `S:\Silver_Tier\.env` |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Gmail OAuth fails | Delete `gmail_token.json`, re-run setup |
| LinkedIn login fails | Check `.env` credentials |
| No action files | Check `Logs/` folder |
| Dependencies fail | `pip install --upgrade pip` |

---

## Version History

| Version | Status | Features |
|---------|--------|----------|
| Silver | 🟢 Live | Gmail + LinkedIn |
| Gold | 🟡 Upcoming | Multi-platform Integration |

---

## Support

- Check `AI_Employee_Vault/Logs/` for errors
- Verify `.env` file has correct credentials
- Run commands with `--help` for options

---

**End of Documentation**