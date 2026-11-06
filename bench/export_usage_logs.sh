#!/bin/bash
# Export Code Interpreter USAGE_LOGS (one record per session-second) for analyze.py / reconcile.py.
# Usage: bench/export_usage_logs.sh <start-epoch-ms> <end-epoch-ms> [output]
# The export contains account ID and resource ARNs; results/usage_logs*.json is git-ignored.
set -euo pipefail
PROFILE=${AWS_PROFILE:-test}
REGION=${AWS_REGION:-ap-northeast-1}
LOG_GROUP=${LOG_GROUP:-/aws/vendedlogs/bedrock-agentcore/code-interpreter/ci_cost_test}
OUT=${3:-results/usage_logs_full_day.json}
aws logs filter-log-events --profile "$PROFILE" --region "$REGION" --log-group-name "$LOG_GROUP" \
  --start-time "$1" --end-time "$2" --output json --query "events[].message" > "$OUT"
echo "wrote $OUT"
