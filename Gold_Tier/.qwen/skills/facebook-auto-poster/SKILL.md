# Facebook Auto Poster Skill

## Overview
Posts business updates to Facebook (Personal Profile + Pages) using Playwright browser automation.
Requires human approval before posting (HITL pattern).

## Triggers
- POST_*.md files in Needs_Action folder
- AI creates Facebook post drafts for approval

## Input
- `AI_Employee_Vault/Needs_Action/POST_*.md` - Post content requiring approval
- `AI_Employee_Vault/Approved/FACEBOOK_POST_*.md` - Approved posts ready to publish

## Output
- Posts published to Facebook (Profile or Page)
- Screenshots saved to `.facebook_session/` for verification
- `AI_Employee_Vault/Done/` - Completed post actions
- `AI_Employee_Vault/Logs/` - Activity logs

## Usage
```bash
# Test authentication
python scripte/facebook_poster.py --vault PATH --test

# Dry run mode
python scripte/facebook_poster.py --vault PATH --dry-run

# Live mode (via orchestrator)
python scripte/orchestrator.py --vault PATH
```

## Configuration
Set in `.env`:
```
FACEBOOK_EMAIL=your@email.com
FACEBOOK_PASSWORD=your_password
FACEBOOK_PAGE_NAME=YourBusinessPage  # Optional, defaults to personal profile
DRY_RUN=false  # Set to true for testing
```

## Dependencies
- playwright>=1.40.0
- python-dotenv

## Setup
1. Install Playwright: `pip install playwright`
2. Install browsers: `playwright install chromium`
3. Set Facebook credentials in `.env`
4. First run will require manual Facebook login in the browser
5. Subsequent runs use session cookies

## HITL Workflow
1. AI creates POST_*.md in Needs_Action/
2. Facebook Poster creates approval request in Pending_Approval/
3. Human reviews and moves file to Approved/
4. Orchestrator triggers Facebook Poster to publish
5. Post confirmation screenshot saved to .facebook_session/

## Warning
Be aware of Facebook's terms of service regarding automation. Use at your own risk.
Facebook may detect and block automated posting. Consider using their official Graph API for Pages.
