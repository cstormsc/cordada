#!/bin/sh
# Database dump plus uploaded files, into /backups. Parte B §10.
#   backup.sh once   one backup, then exit (make backup)
#   backup.sh        one now, then every BACKUP_INTERVAL_HOURS; prunes old ones
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

wait_for_db() {
    # After Docker restarts on its own (e.g. the computer woke up), the database can take a
    # moment; compose's depends_on only applies to `docker compose up`.
    tries=0
    until pg_isready -q; do
        tries=$((tries + 1))
        [ "$tries" -ge 30 ] && return 1
        sleep 2
    done
}

run_backup() {
    # Every step is checked explicitly: called as `run_backup || ...`, the shell ignores
    # set -e inside this function, and a failed pg_dump once left an empty "backup".
    stamp=$(date +%Y%m%d-%H%M%S)
    tmp="/backups/.cordada-$stamp"
    wait_for_db || { echo "$(date -Iseconds) database not reachable" >&2; return 1; }
    pg_dump -Fc -f "$tmp.dump" || { rm -f "$tmp.dump"; return 1; }
    [ -s "$tmp.dump" ] || { rm -f "$tmp.dump"; return 1; }
    tar -czf "$tmp-media.tar.gz" -C /media . || { rm -f "$tmp.dump" "$tmp-media.tar.gz"; return 1; }
    # Rename only when both are complete, so a half-written backup never looks valid.
    mv "$tmp.dump" "/backups/cordada-$stamp.dump"
    mv "$tmp-media.tar.gz" "/backups/cordada-$stamp-media.tar.gz"
    echo "$(date -Iseconds) backup cordada-$stamp"
}

prune() {
    find /backups -maxdepth 1 -name 'cordada-*' -mtime +"$KEEP_DAYS" -print -delete
    find /backups -maxdepth 1 -name '.cordada-*' -mmin +60 -delete
}

if [ "${1:-}" = "once" ]; then
    run_backup || { echo "$(date -Iseconds) backup FAILED" >&2; exit 1; }
    exit 0
fi

while true; do
    if run_backup; then
        prune
        sleep $((INTERVAL_HOURS * 3600))
    else
        echo "$(date -Iseconds) backup FAILED; retrying in 10 minutes" >&2
        sleep 600
    fi
done
