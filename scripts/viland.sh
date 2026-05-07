#!/usr/bin/env bash
if pgrep -x viland > /dev/null; then
    echo "Viland already running"
else
    exec python3 -m viland.daemon &
fi