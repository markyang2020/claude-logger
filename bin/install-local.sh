#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"

chmod +x "$PLUGIN_DIR"/bin/*.py "$PLUGIN_DIR"/bin/*.sh

claude plugin validate "$PLUGIN_DIR"
claude plugin marketplace add "$PLUGIN_DIR"
claude plugin install claude-logger@mark-local-plugins

echo "Installed claude-logger@mark-local-plugins"
echo "Restart Claude Code, then run /hooks to verify."
echo "Logs: ~/.claude/logs/<session-id>/summary.md"
