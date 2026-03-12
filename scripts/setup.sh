#!/bin/bash
set -e

# 1. Check .env file
if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example and fill in your tokens."
    exit 1
fi

# 2. Setup Tailscale Funnel
echo "Setting up Tailscale Funnel on port 8080..."
tailscale funnel 8080

# 3. Get Funnel URL
FUNNEL_URL=$(tailscale funnel status | grep "https://" | awk '{print $2}')
echo "Funnel URL: $FUNNEL_URL"
echo "Use this URL for Notion webhook subscription: ${FUNNEL_URL}/webhook/notion"

# 4. Copy plist to LaunchAgents
PLIST_SRC="com.seokmogu.notion-meeting-sync.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.seokmogu.notion-meeting-sync.plist"
cp "$PLIST_SRC" "$PLIST_DEST"
echo "Copied plist to $PLIST_DEST"

# 5. Load launchd service
launchctl load "$PLIST_DEST"
echo "Service loaded. Check logs at /tmp/notion-meeting-sync.log"

# 6. Notion webhook setup guide
echo ""
echo "Next steps:"
echo "1. Go to Notion Integration settings"
echo "2. Add webhook subscription:"
echo "   - URL: ${FUNNEL_URL}/webhook/notion"
echo "   - Event: page.created"
echo "   - Database: Select your meeting notes database"
echo "3. Copy the verification_token and update NMS_WEBHOOK_SECRET in plist"
echo "4. Reload service: launchctl unload $PLIST_DEST && launchctl load $PLIST_DEST"
