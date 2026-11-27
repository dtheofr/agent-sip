#!/usr/bin/env bash
# PostToolUse hook: lint-fix and format the Python file Claude just edited.
# Never blocks: a missing ruff or a lint error is left for `make check`.
f=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))' 2>/dev/null)
case "$f" in
  *.py) ;;
  *) exit 0 ;;
esac
root="${CLAUDE_PROJECT_DIR:-.}"
ruff="$root/.venv/bin/ruff"
[ -x "$ruff" ] || ruff=$(command -v ruff) || exit 0
"$ruff" check --fix -q "$f" >/dev/null 2>&1
"$ruff" format -q "$f" >/dev/null 2>&1
exit 0
