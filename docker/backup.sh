#!/bin/sh
# Database dump plus uploaded files, into /backups. Parte B §10.
#   backup.sh once   one backup, then exit (make backup)
#   backup.sh        one now, then every BACKUP_INTERVAL_HOURS; prunes old ones
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

run_backup() {
    stamp=$(date +%Y%m%d-%H%M%S)
    tmp="/backups/.cordada-$stamp"
    pg_dump -Fc -f "$tmp.dump"
    tar -czf "$tmp-media.tar.gz" -C /media .
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
    run_backup
    exit 0
fi

while true; do
    run_backup || echo "$(date -Iseconds) backup FAILED" >&2
    prune
    sleep $((INTERVAL_HOURS * 3600))
done
