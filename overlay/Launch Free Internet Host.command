#!/bin/bash
launcher_dir="$(cd "$(dirname "$0")" && pwd)" || exit 1
exec "$launcher_dir/Launch Co-op.command" --free-internet-host "$@"
