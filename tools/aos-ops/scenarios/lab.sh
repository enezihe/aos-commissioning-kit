#!/usr/bin/env bash
# Build the lab faults on a LOCAL kind cluster. Refuses anything else.
#   ./lab.sh up 05      apply scenario 05 into namespace lab (replaces what was there)
#   ./lab.sh down       delete namespace lab
set -euo pipefail
CTX="${LAB_CONTEXT:-kind-aos-dev}"
case "$CTX" in kind-*) ;; *) echo "refused: '$CTX' is not a local kind context" >&2; exit 2 ;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
case "${1:-}" in
  up)
    file=$(ls "$HERE"/"${2:?give a scenario number such as 05}"-*.yaml | head -1)
    kubectl --context "$CTX" delete namespace lab --wait=true >/dev/null 2>&1 || true
    kubectl --context "$CTX" create namespace lab >/dev/null
    kubectl --context "$CTX" apply -f "$file" >/dev/null
    echo "applied $(basename "$file") to $CTX / lab"
    ;;
  down)
    kubectl --context "$CTX" delete namespace lab --wait=false
    ;;
  *) echo "usage: $0 up <number> | down" >&2; exit 2 ;;
esac
