#!/usr/bin/env bash
# preflight.sh — wrapper bash equivalent a preflight.ps1
# Appelle omega-fix.ps1 via powershell, verifie la RAM, puis execute la commande.

set +e

MIN_RAM_MB="${PREFLIGHT_MIN_RAM_MB:-3000}"
OMEGA_FIX="C:/AI/nanobot-omega/scripts/omega-fix.ps1"
LOG_DIR="C:/AI/nanobot-omega/logs"
LOG_FILE="$LOG_DIR/preflight.log"
mkdir -p "$LOG_DIR" 2>/dev/null

log() {
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] $*" >> "$LOG_FILE"
}

if [ "$#" -eq 0 ]; then
    echo "preflight: aucune commande fournie." >&2
    exit 2
fi

CMD_LINE="$*"
log "START: $CMD_LINE"

if [ "$PREFLIGHT_OFF" = "1" ]; then
    log "PREFLIGHT_OFF=1, execution directe"
    exec "$@"
fi

echo "[preflight] Nettoyage systeme (omega-fix)..." >&2
powershell -ExecutionPolicy Bypass -NoProfile -File "$OMEGA_FIX" -Silent >/dev/null 2>&1
log "omega-fix done (exit=$?)"

# Verification RAM via powershell
FREE_MB=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)" 2>/dev/null | tr -d '\r\n ')
if [ -n "$FREE_MB" ] && [ "$FREE_MB" -lt "$MIN_RAM_MB" ] 2>/dev/null; then
    echo "[preflight] RAM faible (${FREE_MB}MB < ${MIN_RAM_MB}MB) - passe agressive..." >&2
    powershell -ExecutionPolicy Bypass -NoProfile -File "$OMEGA_FIX" -Aggressive -Silent >/dev/null 2>&1
    log "aggressive cleanup"
fi

# Injection NODE_OPTIONS pour builds Node
case "$1" in
    npm|npx|yarn|pnpm|vite|next|firebase|vercel|netlify)
        export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"
        log "NODE_OPTIONS=$NODE_OPTIONS"
        ;;
esac

echo "[preflight] -> $CMD_LINE" >&2
log "EXEC: $CMD_LINE"

export PREFLIGHT_RUNNING=1
"$@"
CODE=$?
log "END: exit=$CODE"
exit $CODE
