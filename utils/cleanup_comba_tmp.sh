#!/usr/bin/env bash
# Enforce a disk budget on COMBA pipeline work dirs (/tmp/comba_*).
# Policy: when total size exceeds LIMIT_GB (default 50), delete the OLDEST
# dirs first until usage drops under TARGET_GB (default 40, gives headroom
# so the script doesn't re-trigger on every run).
#
# Usage:  utils/cleanup_comba_tmp.sh            # enforce with defaults
#         LIMIT_GB=30 TARGET_GB=20 utils/cleanup_comba_tmp.sh
#         utils/cleanup_comba_tmp.sh --dry-run  # show what would be deleted
set -euo pipefail
# Force C locale: the printf builtin under vi_VN expects comma decimals and
# rejects awk's dot-decimal output, aborting the script via set -e.
export LC_ALL=C

LIMIT_GB="${LIMIT_GB:-50}"
TARGET_GB="${TARGET_GB:-40}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

shopt -s nullglob
dirs=(/tmp/comba_*)
if [ ${#dirs[@]} -eq 0 ]; then
    echo "No /tmp/comba_* dirs — nothing to do."
    exit 0
fi

tkb=$(du -sk "${dirs[@]}" 2>/dev/null | awk '{s+=$1} END {print s+0}')
limit_kb=$((LIMIT_GB * 1024 * 1024))
target_kb=$((TARGET_GB * 1024 * 1024))

printf "COMBA tmp usage: %.1f GB across %d dirs (limit %s GB)\n" \
    "$(echo "$tkb" | awk '{print $1/1024/1024}')" "${#dirs[@]}" "$LIMIT_GB"

if [ "$tkb" -le "$limit_kb" ]; then
    echo "Under limit — nothing deleted."
    exit 0
fi

echo "Over limit — removing oldest work dirs until under ${TARGET_GB} GB..."
deleted=0
while IFS= read -r d; do
    [ "$tkb" -le "$target_kb" ] && break
    sz=$(du -sk -- "$d" 2>/dev/null | awk '{print $1}')
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  [dry-run] would delete: $d ($((${sz:-0}/1024)) MB)"
    else
        rm -rf -- "$d"
    fi
    tkb=$((tkb - ${sz:-0}))
    deleted=$((deleted + 1))
done < <(ls -dtr /tmp/comba_* 2>/dev/null)

printf "%s %d dirs; usage now %.1f GB.\n" \
    "$([ "$DRY_RUN" -eq 1 ] && echo 'Would delete' || echo 'Deleted')" \
    "$deleted" "$(echo "$tkb" | awk '{print $1/1024/1024}')"
