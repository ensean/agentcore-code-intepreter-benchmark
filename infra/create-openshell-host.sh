#!/bin/bash
# Self-hosted comparison host: Ubuntu 24.04 + Docker + NVIDIA OpenShell.
# m8i.large = 2 vCPU / 8 GiB, the same size as one Code Interpreter sandbox; m8i supports nested
# virtualization, which the OpenShell MicroVM driver needs (add --cpu-options NestedVirtualization=enabled
# via `aws ec2 modify-instance-cpu-options` while the instance is stopped, or launch with it).
# Usage: SG_ID=sg-xxx SUBNET_ID=subnet-xxx ./create-openshell-host.sh [instance-type]
set -euo pipefail
PROFILE=${AWS_PROFILE:-test}
REGION=${AWS_REGION:-ap-northeast-1}
AWS="aws --profile $PROFILE --region $REGION"
SG=${SG_ID:?set SG_ID (e.g. the bastion SG: SSH from operator /32 only)}
SUBNET=${SUBNET_ID:?set SUBNET_ID}
KEY_NAME=${KEY_NAME:-ec2-starter-key}
TYPE=${1:-m8i.large}

AMI=$($AWS ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)
ID=$($AWS ec2 run-instances --image-id "$AMI" --instance-type "$TYPE" --key-name "$KEY_NAME" \
  --security-group-ids "$SG" --subnet-id "$SUBNET" --associate-public-ip-address \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":40,"VolumeType":"gp3","DeleteOnTermination":true,"Encrypted":true}}]' \
  --tag-specifications '[{"ResourceType":"instance","Tags":[{"Key":"Name","Value":"ci-cost-openshell"},{"Key":"project","Value":"ci-cost-test"}]}]' \
  --query "Instances[0].InstanceId" --output text)
$AWS ec2 wait instance-running --instance-ids "$ID"
echo "$ID $($AWS ec2 describe-instances --instance-ids "$ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
