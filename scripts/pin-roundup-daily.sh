#!/bin/bash
# pin-roundup-daily.sh - write the daily Disney pin roundup with the standalone
# Claude CLI, decoupled from the Claude desktop app (same pattern as
# plex-cli-nightly.sh). Run by launchd job com.disney-pin-news.daily.
#
# TOKEN: shared durable token from `claude setup-token`, at
# ~/.config/claude-kanban/oauth-token, exported as CLAUDE_CODE_OAUTH_TOKEN.
# Instagram comes from scripts/instagram_posts.py (Meta Business Discovery via
# the "Disney Pin News Reader" Meta app; token in the login Keychain, set up
# with scripts/instagram_setup.py). Without it the run skips Instagram.

set -euo pipefail

export TZ="America/New_York"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$HOME/go/bin"

REPO="/Users/Shared/Projects/rssfeeds"
TOKEN_FILE="$HOME/.config/claude-kanban/oauth-token"
PROMPT_FILE="$REPO/scripts/roundup-prompt.md"
NOTIFY="$HOME/.claude/imessage-notify.sh"
LOG_DIR="$HOME/Library/Logs/claude-pins"
mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

if [[ ! -s "$TOKEN_FILE" ]]; then
  echo "$(ts) FATAL: no token at $TOKEN_FILE - run: claude setup-token" >&2
  exit 78  # EX_CONFIG
fi
export CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"

cd "$REPO"
echo "$(ts) pin-roundup start"

# Tools are allow-listed instead of skipping permissions: this job reads
# untrusted web/social content, so it only gets what the roundup needs.
ALLOWED=(
  Read Write Edit Glob Grep WebFetch WebSearch Skill
  "Bash(git pull:*)" "Bash(git add:*)" "Bash(git commit:*)" "Bash(git push:*)"
  "Bash(git status:*)" "Bash(git log:*)" "Bash(git diff:*)"
  "Bash(reddit-pp-cli:*)" "Bash(date:*)" "Bash(ls:*)"
  "Bash(python3.12 scripts/og_image.py:*)" "Bash(python3.12 scripts/instagram_posts.py:*)"
)

set +e
OUT=$("$HOME/.local/bin/claude" \
  --print \
  --output-format text \
  --allowedTools "${ALLOWED[@]}" \
  < "$PROMPT_FILE")
rc=$?
set -e
echo "$OUT"
echo "$(ts) pin-roundup end rc=$rc"

if [[ -x "$NOTIFY" ]]; then
  MSG="Disney pin roundup (rc=$rc): ${OUT: -600}"
  printf '{"message":%s}' "$(printf '%s' "$MSG" | python3.12 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" \
    | "$NOTIFY" "Pin roundup" >/dev/null 2>&1 || echo "$(ts) iMessage notify failed" >&2
fi
exit $rc
