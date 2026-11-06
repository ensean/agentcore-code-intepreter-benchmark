#!/bin/bash
# Daily Code Interpreter usage/cost in Tokyo from Cost Explorer (data lags ~24h).
# Usage: bench/check_cost_explorer.sh [start YYYY-MM-DD] [end YYYY-MM-DD exclusive]
set -euo pipefail
START=${1:-2026-10-29}
END=${2:-2026-11-07}
aws ce get-cost-and-usage --profile "${AWS_PROFILE:-test}" --region us-east-1 \
  --time-period "Start=$START,End=$END" --granularity DAILY \
  --metrics UnblendedCost UsageQuantity \
  --filter '{"Dimensions":{"Key":"USAGE_TYPE","Values":["APN1-CodeInterpreter:Consumption-based:vCPU","APN1-CodeInterpreter:Consumption-based:Memory"]}}' \
  --group-by Type=DIMENSION,Key=USAGE_TYPE \
  --query 'ResultsByTime[].{day:TimePeriod.Start,groups:Groups[].{type:Keys[0],usage:Metrics.UsageQuantity.Amount,cost:Metrics.UnblendedCost.Amount}}' \
  --output json
