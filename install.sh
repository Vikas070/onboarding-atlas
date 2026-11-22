#!/usr/bin/env sh
# Install onboarding-atlas into a project (or globally for Claude Code). Copies files only; no network, no sudo.
#
#   ./install.sh                     # into the current directory, for all supported agents
#   ./install.sh /path/to/project    # into another project
#   ./install.sh --claude            # only Claude Code    (.claude/skills/onboarding-atlas)
#   ./install.sh --codex             # only Codex & other AGENTS.md agents (.agents/skills + AGENTS.md note)
#   ./install.sh --cursor            # only Cursor         (.agents/skills + .cursor/rules/onboarding-atlas.mdc)
#   ./install.sh --global-claude     # ~/.claude/skills/onboarding-atlas (every project)
set -eu

SRC="$(cd "$(dirname "$0")" && pwd)"
TARGET="."
DO_CLAUDE=0; DO_CODEX=0; DO_CURSOR=0; DO_GLOBAL=0; ANY=0
for a in "$@"; do
  case "$a" in
    --claude) DO_CLAUDE=1; ANY=1 ;;
    --codex) DO_CODEX=1; ANY=1 ;;
    --cursor) DO_CURSOR=1; ANY=1 ;;
    --global-claude) DO_GLOBAL=1; ANY=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    -*) echo "unknown option: $a" >&2; exit 2 ;;
    *) TARGET="$a" ;;
  esac
done
[ "$ANY" -eq 0 ] && { DO_CLAUDE=1; DO_CODEX=1; DO_CURSOR=1; }
[ -d "$TARGET" ] || { echo "not a directory: $TARGET" >&2; exit 2; }
TARGET="$(cd "$TARGET" && pwd)"

copy_skill() {  # $1 = destination dir
  mkdir -p "$1"
  for item in SKILL.md scripts templates references; do
    rm -rf "$1/$item"; cp -R "$SRC/$item" "$1/$item"
  done
  find "$1" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  echo "installed -> $1"
}

[ "$DO_GLOBAL" -eq 1 ] && copy_skill "$HOME/.claude/skills/onboarding-atlas"
[ "$DO_CLAUDE" -eq 1 ] && copy_skill "$TARGET/.claude/skills/onboarding-atlas"
if [ "$DO_CODEX" -eq 1 ] || [ "$DO_CURSOR" -eq 1 ]; then
  copy_skill "$TARGET/.agents/skills/onboarding-atlas"
fi
if [ "$DO_CODEX" -eq 1 ]; then
  if [ -f "$TARGET/AGENTS.md" ] && grep -q "onboarding-atlas" "$TARGET/AGENTS.md"; then
    echo "AGENTS.md already mentions onboarding-atlas (left unchanged)"
  else
    cat "$SRC/adapters/AGENTS.md.snippet" >> "$TARGET/AGENTS.md"; echo "updated -> $TARGET/AGENTS.md"
  fi
fi
if [ "$DO_CURSOR" -eq 1 ]; then
  mkdir -p "$TARGET/.cursor/rules"
  cp "$SRC/adapters/cursor-rule.mdc" "$TARGET/.cursor/rules/onboarding-atlas.mdc"
  echo "installed -> $TARGET/.cursor/rules/onboarding-atlas.mdc"
fi
echo
echo "Done. In your coding agent, say:  Use the onboarding-atlas skill to document this repo."
