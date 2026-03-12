# Notion Meeting Sync

Automatically sync Notion meeting notes to GitLab repository.

## Features
- Webhook-based sync (Notion Integration Webhook → Tailscale Funnel → local FastAPI)
- Catch-up polling for missed events
- Custom tag conversion (`<meeting-notes>` → standard markdown)
- Git commit + push to remote repository

## Prerequisites
- Python 3.13+
- Tailscale installed and authenticated
- Notion Integration with database access
- Git repository for meeting notes

## Installation

1. **Clone and setup**:
   ```bash
   cd /Users/seokmogu/project/notion-meeting-sync
   uv sync
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and fill in:
   # NMS_NOTION_TOKEN=your_notion_integration_token
   # NMS_NOTION_DATABASE_ID=your_database_id
   # NMS_WEBHOOK_SECRET=your_verification_token (from Notion webhook setup)
   # NMS_GIT_REPO_PATH=/path/to/agentic-services-docs
   ```

3. **Run setup script**:
   ```bash
   chmod +x scripts/setup.sh
   ./scripts/setup.sh
   ```

4. **Configure Notion webhook**:
   - Go to Notion Integration settings
   - Add webhook subscription:
     - URL: `https://your-tailscale-funnel-url/webhook/notion`
     - Event: `page.created`
     - Database: Select your meeting notes database
   - Copy the `verification_token` and update `NMS_WEBHOOK_SECRET` in `.env` and plist
   - Reload service: `launchctl unload ~/Library/LaunchAgents/com.seokmogu.notion-meeting-sync.plist && launchctl load ~/Library/LaunchAgents/com.seokmogu.notion-meeting-sync.plist`

## Usage

**Manual sync**:
```bash
uv run python -m notion_meeting_sync sync
```

**Dry-run**:
```bash
uv run python -m notion_meeting_sync sync --dry-run
```

**Full resync**:
```bash
uv run python -m notion_meeting_sync sync --full
```

**Check status**:
```bash
uv run python -m notion_meeting_sync status
```

**Service management**:
```bash
# Check service status
launchctl list | grep notion-meeting-sync

# View logs
tail -f /tmp/notion-meeting-sync.log

# Restart service
launchctl unload ~/Library/LaunchAgents/com.seokmogu.notion-meeting-sync.plist
launchctl load ~/Library/LaunchAgents/com.seokmogu.notion-meeting-sync.plist
```
