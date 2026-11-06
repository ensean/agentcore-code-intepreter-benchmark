#!/bin/bash
# Bastion EC2 for the AgentCore Code Interpreter cost test (ap-northeast-1, profile test).
set -euo pipefail

PROFILE=${AWS_PROFILE:-test}
REGION=${AWS_REGION:-ap-northeast-1}
ACCOUNT=$(aws --profile "$PROFILE" sts get-caller-identity --query Account --output text)
NAME=ci-cost-bastion
KEY_NAME=${KEY_NAME:-ec2-starter-key}
PUB_KEY=${PUB_KEY:?set PUB_KEY to the SSH public key file to import as $KEY_NAME}
SG_NAME=ci-cost-bastion-sg
ROLE=ci-cost-bastion-role
MY_IP=$(curl -s https://checkip.amazonaws.com)
AWS="aws --profile $PROFILE --region $REGION"

echo "My IP: $MY_IP"

# Key pair
if ! $AWS ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  $AWS ec2 import-key-pair --key-name "$KEY_NAME" --public-key-material "fileb://$PUB_KEY" >/dev/null
fi

# Security group: SSH from this machine only
VPC_ID=$($AWS ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG_ID=$($AWS ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  SG_ID=$($AWS ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC_ID" \
    --description "SSH from operator IP for Code Interpreter cost test" --query GroupId --output text)
  $AWS ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --ip-permissions "[{\"IpProtocol\":\"tcp\",\"FromPort\":22,\"ToPort\":22,\"IpRanges\":[{\"CidrIp\":\"$MY_IP/32\",\"Description\":\"operator\"}]}]" >/dev/null
fi
echo "SG: $SG_ID"

# IAM role + instance profile
if ! aws --profile $PROFILE iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws --profile $PROFILE iam create-role --role-name "$ROLE" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws --profile $PROFILE iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws --profile $PROFILE iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
  aws --profile $PROFILE iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
fi
aws --profile $PROFILE iam put-role-policy --role-name "$ROLE" --policy-name ci-cost-test --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Sid\": \"InvokeOpus\", \"Effect\": \"Allow\",
     \"Action\": [\"bedrock:InvokeModel\", \"bedrock:InvokeModelWithResponseStream\"],
     \"Resource\": [
       \"arn:aws:bedrock:$REGION:$ACCOUNT:inference-profile/global.anthropic.claude-opus-5-5\",
       \"arn:aws:bedrock:*::foundation-model/anthropic.claude-opus-5-5\",
       \"arn:aws:bedrock:::foundation-model/anthropic.claude-opus-5-5\"]},
    {\"Sid\": \"CodeInterpreter\", \"Effect\": \"Allow\",
     \"Action\": [\"bedrock-agentcore:StartCodeInterpreterSession\", \"bedrock-agentcore:InvokeCodeInterpreter\",
                \"bedrock-agentcore:StopCodeInterpreterSession\", \"bedrock-agentcore:GetCodeInterpreterSession\",
                \"bedrock-agentcore:ListCodeInterpreterSessions\"],
     \"Resource\": [\"arn:aws:bedrock-agentcore:$REGION:$ACCOUNT:code-interpreter/*\",
                  \"arn:aws:bedrock-agentcore:$REGION:$ACCOUNT:code-interpreter-custom/*\",
                  \"arn:aws:bedrock-agentcore:$REGION:aws:code-interpreter/aws.codeinterpreter.v1\"]},
    {\"Sid\": \"ReadUsageLogs\", \"Effect\": \"Allow\",
     \"Action\": [\"logs:FilterLogEvents\", \"logs:StartQuery\", \"logs:GetQueryResults\", \"logs:DescribeLogStreams\"],
     \"Resource\": \"*\"},
    {\"Sid\": \"ReadMetrics\", \"Effect\": \"Allow\",
     \"Action\": [\"cloudwatch:GetMetricData\", \"cloudwatch:ListMetrics\"], \"Resource\": \"*\"}
  ]}"
sleep 10  # instance profile propagation

AMI_ID=$($AWS ec2 describe-images --owners amazon \
  --filters "Name=name,Values=al2023-ami-2023.*-x86_64" "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text)
SUBNET_ID=$($AWS ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=default-for-az,Values=true" \
  --query 'Subnets[0].SubnetId' --output text)

INSTANCE_ID=$($AWS ec2 run-instances --image-id "$AMI_ID" --instance-type t8i.medium \
  --key-name "$KEY_NAME" --security-group-ids "$SG_ID" --subnet-id "$SUBNET_ID" \
  --associate-public-ip-address --iam-instance-profile "Name=$ROLE" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3","DeleteOnTermination":true,"Encrypted":true}}]' \
  --tag-specifications "[{\"ResourceType\":\"instance\",\"Tags\":[{\"Key\":\"Name\",\"Value\":\"$NAME\"},{\"Key\":\"project\",\"Value\":\"ci-cost-test\"}]}]" \
  --query 'Instances[0].InstanceId' --output text)
$AWS ec2 wait instance-running --instance-ids "$INSTANCE_ID"
IP=$($AWS ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "Instance: $INSTANCE_ID  IP: $IP"
echo "ssh -i <private-key-for-$KEY_NAME> ec2-user@$IP"
