#!/bin/bash
# Custom Code Interpreter (SANDBOX network mode, same runtime as aws.codeinterpreter.v1)
# with USAGE_LOGS delivered to CloudWatch Logs, so per-session vCPU-hours / GB-hours can be read.
set -euo pipefail

PROFILE=${AWS_PROFILE:-test}
REGION=${AWS_REGION:-ap-northeast-1}
ACCOUNT=$(aws --profile "$PROFILE" sts get-caller-identity --query Account --output text)
CI_NAME=ci_cost_test
LOG_GROUP=/aws/vendedlogs/bedrock-agentcore/code-interpreter/ci_cost_test
AWS="aws --profile $PROFILE --region $REGION"

CI_ID=$($AWS bedrock-agentcore-control list-code-interpreters \
  --query "codeInterpreterSummaries[?name=='$CI_NAME'].codeInterpreterId | [0]" --output text)
if [ -z "$CI_ID" ] || [ "$CI_ID" = "None" ]; then
  CI_ID=$($AWS bedrock-agentcore-control create-code-interpreter --name "$CI_NAME" \
    --description "Code Interpreter cost test - HTML and CSV generation" \
    --network-configuration networkMode=SANDBOX \
    --tags project=ci-cost-test --query codeInterpreterId --output text)
fi
for i in $(seq 1 30); do
  STATUS=$($AWS bedrock-agentcore-control get-code-interpreter --code-interpreter-id "$CI_ID" --query status --output text)
  [ "$STATUS" = "READY" ] && break
  sleep 5
done
CI_ARN=$($AWS bedrock-agentcore-control get-code-interpreter --code-interpreter-id "$CI_ID" --query codeInterpreterArn --output text)
echo "Code Interpreter: $CI_ID ($STATUS)"

$AWS logs create-log-group --log-group-name "$LOG_GROUP" 2>/dev/null || true
$AWS logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 30
LG_ARN="arn:aws:logs:$REGION:$ACCOUNT:log-group:$LOG_GROUP"

$AWS logs put-delivery-source --name ci-cost-usage-src --log-type USAGE_LOGS --resource-arn "$CI_ARN" >/dev/null
$AWS logs put-delivery-destination --name ci-cost-usage-dst \
  --delivery-destination-configuration "destinationResourceArn=$LG_ARN" >/dev/null
DST_ARN=$($AWS logs get-delivery-destination --name ci-cost-usage-dst --query deliveryDestination.arn --output text)
EXISTING=$($AWS logs describe-deliveries --query "deliveries[?deliverySourceName=='ci-cost-usage-src'].id | [0]" --output text)
if [ -z "$EXISTING" ] || [ "$EXISTING" = "None" ]; then
  $AWS logs create-delivery --delivery-source-name ci-cost-usage-src --delivery-destination-arn "$DST_ARN" >/dev/null
fi
echo "Usage logs -> $LOG_GROUP"
echo "CI_ID=$CI_ID"
