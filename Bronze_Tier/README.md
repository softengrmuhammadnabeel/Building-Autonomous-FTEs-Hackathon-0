# Autonomous Worker | Foundation Tier

**Version:** 1.0 | **Type:** Autonomous Foundation Layer | **Stack:** Qwen Code + Obsidian

---

## 1.0 System Overview

The AI Employee is an autonomous agent system designed for task processing automation.

### 1.1 Core Capabilities

| Capability | Implementation |
|------------|----------------|
| Input Monitoring | Watcher scripts (files, emails, messages) |
| Task Processing | Qwen Code reasoning engine |
| Action Execution | MCP servers + human approval workflow |
| Documentation | Obsidian vault integration |

### 1.2 Bronze Tier Specifications

| Component | Status |
|-----------|--------|
| Obsidian vault with Dashboard.md and Company_Handbook.md | Completed |
| File System Watcher | Completed |
| Orchestrator with Qwen Code trigger | Completed |
| Folder structure (Inbox/Needs_Action/Done) | Completed |
| Activity logging and audit trail | Completed |

---

## 2.0 Architecture

```
INPUT LAYER
    │
    ▼
PERCEPTION LAYER
├── Filesystem Watcher (Python)
├── Monitors /Drop folder
└── Creates action files in /Needs_Action
    │
    ▼
OBSIDIAN VAULT
├── /Inbox              → Raw incoming
├── /Needs_Action       → Awaiting processing
├── /Plans              → Execution plans
├── /Done               → Completed
├── /Pending_Approval   → Human decision pending
├── /Approved           → Ready to execute
├── /Logs               → Activity records
└── Dashboard.md        → Live status
    │
    ▼
REASONING LAYER
├── Qwen Code
├── Reads action files
├── Creates plans
└── Executes actions
```

---

## 3.0 Directory Structure

```
AI_Workforce/
│
├── Bronze_Tier/
│   ├── .qwen/                              # Qwen Code configuration
│   │
│   ├── AI_Employee_Vault/                  # Obsidian knowledge base
│   │   ├── .obsidian/                      # Obsidian settings
│   │   ├── Accounting/                     # Financial records
│   │   ├── Approved/                       # Human-approved actions
│   │   ├── Briefings/                      # CEO briefings & updates
│   │   ├── Done/                           # Completed tasks
│   │   ├── Drop/                           # Monitored incoming folder
│   │   ├── Failed/                         # Failed executions
│   │   ├── Inbox/                          # Raw incoming files
│   │   ├── Invoices/                       # Billing & payments
│   │   ├── Logs/                           # Activity audit trails
│   │   ├── Needs_Action/                   # Tasks awaiting processing
│   │   ├── Pending_Approval/               # Waiting for human decision
│   │   ├── Plans/                          # Qwen Code execution plans
│   │   ├── Processing/                     # Currently being processed
│   │   ├── Rejected/                       # Denied actions
│   │   ├── Business_Goals.md               # Objectives & KPIs
│   │   ├── Company_Handbook.md             # Rules of engagement
│   │   └── Dashboard.md                    # Real-time system status
│   │
│   ├── script/                             # Automation scripts
│   │
│   ├── Personal AI Employee Hackathon 0_Build...  # Build notes
│   ├── QWEN.md                             # Qwen Code documentation
│   └── README.md                           # Main documentation
│
├── Silver_Tier/                            # Email automation
└── Gold_Tier/                              # Future upgrade
```

---

## 4.0 Installation & Setup

### 4.1 Prerequisites

| Software | Version | Source |
|----------|---------|--------|
| Python | 3.13+ | https://www.python.org/downloads/ |
| Qwen Code | Latest | https://qwen.ai/qwencode |
| Obsidian | Latest | https://obsidian.md/download |

### 4.2 Installation Steps

**Step 1:** Clone or download this repository

**Step 2:** Install Python dependencies

```bash
cd AI_Workforce\Bronze_Tier\script
pip install -r requirements.txt
```

**Step 3:** Open Obsidian vault (optional)

- Launch Obsidian
- Click "Open folder as vault"
- Select the `AI_Workforce\Bronze_Tier\AI_Employee_Vault` folder

---

## 5.0 Execution Commands

### 5.1 Start Filesystem Watcher

**Terminal 1:**

```bash
cd "S:\AI_Workforce\Bronze_Tier\script"
python watchers/filesystem_watcher.py --vault "S:\AI_Workforce\Bronze_Tier\AI_Employee_Vault"
```

### 5.2 Start Orchestrator

**Terminal 2:**

```bash
cd "S:\AI_Workforce\Bronze_Tier\script"
python orchestrator.py --vault "../AI_Employee_Vault"
python orchestrator.py --vault "../AI_Employee_Vault" --watch
```

### 5.3 Demo Execution Flow

1. Creates a test file in `/Drop`
2. Detects it with the Filesystem Watcher
3. Creates an action file in `/Needs_Action`
4. Processes it with Qwen Code
5. Creates a plan in `/Plans`

---

## 6.0 Workflow Documentation

### 6.1 Standard Processing Flow

| Step | Action |
|------|--------|
| 1 | Place any file in the `/Drop` folder |
| 2 | Filesystem Watcher detects the new file within 30 seconds |
| 3 | Watcher creates a `.md` action file in `/Needs_Action` |
| 4 | Orchestrator triggers Qwen Code to process the action file |
| 5 | Qwen Code reads, plans, and executes (with approvals as needed) |
| 6 | File moves to `/Done` |
| 7 | Dashboard updates |

### 6.2 Folder State Transitions

```
/Drop → /Needs_Action → /Done
                ↓
        /Pending_Approval
                ↓
        /Approved or /Rejected
```

### 6.3 Approval Workflow

| Action | Procedure |
|--------|-----------|
| Request created | Qwen Code creates a file in `/Pending_Approval/` |
| Review | Review the file in Obsidian |
| Approve | Move file to `/Approved/` |
| Reject | Move file to `/Rejected/` |
| Execution | Orchestrator executes approved actions |

---

## 7.0 Configuration Parameters

### 7.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VAULT_PATH` | - | Path to Obsidian vault |
| `WATCHER_CHECK_INTERVAL` | 30 | Watcher check interval (seconds) |
| `ORCHESTRATOR_CHECK_INTERVAL` | 60 | Orchestrator check interval (seconds) |
| `DRY_RUN` | true | Enable dry-run mode |
| `LOG_LEVEL` | INFO | Logging level |

---

## 8.0 Monitoring & Logging

### 8.1 Log Files Location

| Log Type | Path |
|----------|------|
| Watcher Logs | `AI_Employee_Vault/Logs/watcher_YYYY-MM-DD.log` |
| Orchestrator Logs | `AI_Employee_Vault/Logs/orchestrator_YYYY-MM-DD.log` |
| Activity Logs | `AI_Employee_Vault/Logs/YYYY-MM-DD.json` |

### 8.2 Dashboard Metrics

Open `Dashboard.md` in Obsidian to view:

- Pending actions count
- Tasks completed today
- Pending approvals
- Recent activity
- System status

---

## 9.0 Troubleshooting Guide

### 9.1 Qwen Code Processing Issues

| Symptom | Resolution |
|---------|------------|
| No processing | Verify `--ai-agent qwen` flag is specified |
| Errors | Review the orchestrator log file |
| Action not read | Ensure action files have `.md` extension |

### 9.2 Watcher Detection Issues

| Symptom | Resolution |
|---------|------------|
| No detection | Check the watcher log file for errors |
| Path errors | Verify the vault path is correct |
| Folder missing | Ensure the `/Drop` folder exists |
| Permission denied | Check file permissions |

### 9.3 Orchestrator Issues

| Symptom | Resolution |
|---------|------------|
| Not responding | Check for "Qwen Code: Available" in logs |
| Extension error | Ensure action files have `.md` extension |
| Flag missing | Run with `--ai-agent qwen` flag |

---

## 10.0 Upgrade Path: Silver Tier

To upgrade from Bronze to Silver Tier, implement the following:

| Feature | Status |
|---------|--------|
| Gmail Watcher (email monitoring) | Pending |
| WhatsApp Watcher (message monitoring) | Pending |
| MCP server for sending emails | Pending |
| Human-in-the-loop approval workflow | Pending |
| Scheduled tasks (cron/Task Scheduler) | Pending |

---

## 11.0 Security Protocol

| Rule | Rationale |
|------|-----------|
| Never commit `.env` files to version control | Credential protection |
| Review all approvals before moving to `/Approved` | Prevent unauthorized execution |
| Regularly audit logs in `/Logs` | Early issue detection |
| Keep credentials in secure storage | Use keychain, secret manager |

---

## 12.0 Documentation References

| Document | Content |
|----------|---------|
| Company Handbook | Rules of engagement |
| Business Goals | Objectives and metrics |
| Dashboard | Real-time status |

**File Locations:**

- `AI_Workforce/Bronze_Tier/AI_Employee_Vault/Company_Handbook.md`
- `AI_Workforce/Bronze_Tier/AI_Employee_Vault/Business_Goals.md`
- `AI_Workforce/Bronze_Tier/AI_Employee_Vault/Dashboard.md`

---

## 13.0 Contributing

This project is part of the **Personal AI Employee Hackathon 0**.

Contributions and improvements are welcome.

---

**End of Documentation**