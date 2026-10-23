#!/usr/bin/env bash
# Sunshine keeps the Desktop app running after Moonlight disconnects (so it can resume), and
# only runs the prep command's "undo" when the app is closed. This closes the app on every
# disconnect, so the TV screen unplugs when the TV leaves (Back, a crash or a dropped
# connection), and the next connection plugs it in afresh.
# Run by tv-screen-follow.service. Reads the web UI login from the file below; never prints it.
set -uo pipefail

login="$HOME/.config/sunshine-webui-login.txt"

close_app() {
  local user pass
  user=$(grep -iE '^user(name)?\s*:' "$login" | head -1 | sed -E 's/^[^:]*:\s*//')
  pass=$(grep -iE '^password\s*:' "$login" | head -1 | sed -E 's/^[^:]*:\s*//')
  printf 'user = "%s:%s"\n' "$user" "$pass" |
    curl -sk -K - -X POST -H 'Content-Type: application/json' -d '{}' \
      -o /dev/null -w '%{http_code}' https://localhost:47990/api/apps/close
}

journalctl --user -u app-dev.lizardbyte.app.Sunshine -f -n 0 -o cat | while read -r line; do
  case "$line" in
    *"CLIENT DISCONNECTED"*)
      sleep 2
      echo "TV disconnected: closing Desktop (HTTP $(close_app))" ;;
  esac
done
