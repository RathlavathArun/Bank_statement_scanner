#!/usr/bin/env bash
set -eu

AWS_REGION="ap-south-1"
CLUSTER_NAME="bank-statement-cluster"
PROJECT_NAME="bank-statement"
SG_NAME="${PROJECT_NAME}-ecs-tasks-sg"
SUBNET_PREFIX="${PROJECT_NAME}-private-subnet"
NAMESPACE_NAME="${PROJECT_NAME}.local"

echo "Looking up networking details..."
SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values=$SG_NAME --region $AWS_REGION --query 'SecurityGroups[0].GroupId' --output text)
SUBNET_IDS=$(aws ec2 describe-subnets --filters Name=tag:Name,Values="${SUBNET_PREFIX}-*" --region $AWS_REGION --query 'Subnets[*].SubnetId' --output text | tr '\t' ',')
NAMESPACE_ID=$(aws servicediscovery list-namespaces --region $AWS_REGION --query "Namespaces[?Name=='$NAMESPACE_NAME'].Id" --output text)

if [ "$NAMESPACE_ID" == "None" ] || [ -z "$NAMESPACE_ID" ]; then
    echo "Error: Could not find Cloud Map namespace $NAMESPACE_NAME"
    exit 1
fi

echo "Creating Cloud Map Service for ClamAV..."
CLAMAV_SVC_ID="srv-7h2x33p5s477l5lm"
echo "Cloud Map service exists: $CLAMAV_SVC_ID"

echo "Registering ClamAV Task Definition (X86_64)..."
EXEC_ROLE_ARN=$(aws iam get-role --role-name ${PROJECT_NAME}-ecsTaskExecutionRole --query 'Role.Arn' --output text)
TASK_ROLE_ARN=$(aws iam get-role --role-name ${PROJECT_NAME}-ecsTaskRole --query 'Role.Arn' --output text)

cat <<EOF > clamav-task-def.json
{
  "family": "${PROJECT_NAME}-clamav",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "3072",
  "executionRoleArn": "$EXEC_ROLE_ARN",
  "taskRoleArn": "$TASK_ROLE_ARN",
  "runtimePlatform": {
    "operatingSystemFamily": "LINUX",
    "cpuArchitecture": "X86_64"
  },
  "containerDefinitions": [
    {
      "name": "clamav",
      "image": "clamav/clamav:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 3310,
          "hostPort": 3310,
          "protocol": "tcp"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/${PROJECT_NAME}",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "clamav"
        }
      }
    }
  ]
}
EOF

TASK_DEF_ARN=$(aws ecs register-task-definition --cli-input-json file://clamav-task-def.json --region $AWS_REGION --query 'taskDefinition.taskDefinitionArn' --output text)
echo "Registered Task Definition: $TASK_DEF_ARN"

echo "Creating ECS Service for ClamAV..."
aws ecs create-service \
    --cluster $CLUSTER_NAME \
    --service-name ${PROJECT_NAME}-clamav-service \
    --task-definition $TASK_DEF_ARN \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_IDS}],securityGroups=[${SG_ID}],assignPublicIp=DISABLED}" \
    --service-registries "registryArn=arn:aws:servicediscovery:${AWS_REGION}:$(aws sts get-caller-identity --query Account --output text):service/${CLAMAV_SVC_ID}" \
    --region $AWS_REGION >/dev/null 2>&1 || aws ecs update-service --cluster $CLUSTER_NAME --service ${PROJECT_NAME}-clamav-service --desired-count 1 --region $AWS_REGION >/dev/null

echo "ClamAV Service creation triggered!"
rm clamav-task-def.json
