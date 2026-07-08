$ErrorActionPreference = "Stop"

$AwsRegion = "ap-south-1"
$AwsAccountId = (aws sts get-caller-identity --query Account --output text).Trim()
if (-not $AwsAccountId -or $AwsAccountId -eq "None") {
    throw "Could not determine the active AWS account"
}
$EcrRegistry = "$AwsAccountId.dkr.ecr.$AwsRegion.amazonaws.com"
$ApiRepo = "$EcrRegistry/bank-statement-api"
$ImageTag = Get-Date -Format "yyyyMMdd-HHmmss"
$ApiImage = "${ApiRepo}:${ImageTag}"
$ApiImageLatest = "${ApiRepo}:latest"
$ClusterName = "bank-statement-cluster"
$ServiceName = "bank-statement-api-service"
$TaskFamily = "bank-statement-api"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

Require-Command aws
Require-Command docker

$PythonCommand = "python3"
if (-not (Get-Command $PythonCommand -ErrorAction SilentlyContinue)) {
    $PythonCommand = "python"
}
Require-Command $PythonCommand

# Log into ECR
Write-Host "Logging into ECR..."
aws ecr get-login-password --region $AwsRegion | docker login --username AWS --password-stdin $EcrRegistry
if ($LASTEXITCODE -ne 0) { throw "Login failed" }

# Build the docker image locally using Docker Desktop
Write-Host "Building API Docker image: $ApiImage"
docker build -f apps/api/Dockerfile -t $ApiImage -t $ApiImageLatest .
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

# Push the docker image
Write-Host "Pushing API Docker image..."
docker push $ApiImage
if ($LASTEXITCODE -ne 0) { throw "Push failed" }
docker push $ApiImageLatest
if ($LASTEXITCODE -ne 0) { throw "Push failed" }

# Update ECS task definition
Write-Host "Updating task definition..."
$Env:API_IMAGE = $ApiImage
$Env:AWS_REGION = $AwsRegion
$Env:TASK_FAMILY = $TaskFamily
& $PythonCommand -c "
import subprocess, json
import os

aws_region = os.environ['AWS_REGION']
api_image = os.environ['API_IMAGE']
task_family = os.environ['TASK_FAMILY']

result = subprocess.run(
    ['aws', 'ecs', 'describe-task-definition', '--task-definition', task_family, '--region', aws_region, '--query', 'taskDefinition', '--output', 'json'],
    capture_output=True,
    text=True,
    check=True,
)
td = json.loads(result.stdout)
keep = ['family', 'taskRoleArn', 'executionRoleArn', 'networkMode', 'containerDefinitions', 'volumes', 'requiresCompatibilities', 'cpu', 'memory', 'runtimePlatform']
new_td = {k: td[k] for k in keep if k in td}
containers = {c['name']: c for c in new_td['containerDefinitions']}
for name in ('uploads-init', 'api', 'celery'):
    if name in containers:
        containers[name]['image'] = api_image

api = containers['api']
env_vars = {e['name']: e for e in api.get('environment', [])}
env_vars['EMAIL_PROVIDER'] = {'name': 'EMAIL_PROVIDER', 'value': 'ses'}
env_vars['AWS_REGION'] = {'name': 'AWS_REGION', 'value': aws_region}
env_vars['AWS_DEFAULT_REGION'] = {'name': 'AWS_DEFAULT_REGION', 'value': aws_region}
env_vars['TEXTRACT_REGION'] = {'name': 'TEXTRACT_REGION', 'value': aws_region}
env_vars['TEXTRACT_ASYNC_ENABLED'] = {'name': 'TEXTRACT_ASYNC_ENABLED', 'value': 'true'}
if not env_vars.get('SMTP_FROM_EMAIL', {}).get('value'):
    smtp_username = env_vars.get('SMTP_USERNAME', {}).get('value', '')
    if smtp_username:
        env_vars['SMTP_FROM_EMAIL'] = {'name': 'SMTP_FROM_EMAIL', 'value': smtp_username}
api['environment'] = list(env_vars.values())
if 'celery' in containers:
    celery_env = {e['name']: e for e in containers['celery'].get('environment', [])}
    celery_env['AWS_DEFAULT_REGION'] = {'name': 'AWS_DEFAULT_REGION', 'value': aws_region}
    celery_env['TEXTRACT_REGION'] = {'name': 'TEXTRACT_REGION', 'value': aws_region}
    celery_env['TEXTRACT_ASYNC_ENABLED'] = {'name': 'TEXTRACT_ASYNC_ENABLED', 'value': 'true'}
    if 'S3_BUCKET' in env_vars:
        celery_env['S3_BUCKET'] = env_vars['S3_BUCKET']
    containers['celery']['environment'] = list(celery_env.values())

with open('api_td_latest.json', 'w') as f:
    json.dump(new_td, f)
"

# Register new task
Write-Host "Registering task..."
$API_ARN = (aws ecs register-task-definition --region $AwsRegion --cli-input-json file://api_td_latest.json --query "taskDefinition.taskDefinitionArn" --output text).Trim()

# Update service
Write-Host "Deploying service with ARN $API_ARN"
aws ecs update-service --region $AwsRegion --cluster $ClusterName --service $ServiceName --task-definition $API_ARN --force-new-deployment | Out-Null

Write-Host "Waiting for API service to stabilize..."
aws ecs wait services-stable --region $AwsRegion --cluster $ClusterName --services $ServiceName

Write-Host "DEPLOYMENT FINISHED SUCCESSFULLY!"
