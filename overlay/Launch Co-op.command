#!/bin/bash
# No installs or downloads. Arguments, including --lan, pass through unchanged.
launcher_dir="$(cd "$(dirname "$0")" && pwd)" || exit 1
for candidate in "$(command -v python3)" /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [ -n "$candidate" ] && [ -x "$candidate" ] || continue
  if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    "$candidate" "$launcher_dir/launch_coop.py" "$@"
    launcher_status=$?
    if [ "$launcher_status" -ne 0 ] && [ -t 0 ]; then
      read -r -p 'Press Return to close this window. ' launcher_reply
    fi
    exit "$launcher_status"
  fi
done
printf '%s\n' 'Python 3.10 or newer is required. Install Python from https://www.python.org/downloads/, then launch again.' >&2
if [ -t 0 ]; then read -r -p 'Press Return to close this window. ' launcher_reply; fi
exit 1
