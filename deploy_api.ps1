$ErrorActionPreference = "Stop"

# Log into ECR
Write-Host "Logging into ECR..."
aws.exe ecr get-login-password --region us-east-1 | docker.exe login --username AWS --password-stdin 911229172121.dkr.ecr.us-east-1.amazonaws.com
if ($LASTEXITCODE -ne 0) { throw "Login failed" }

# Build the docker image locally using Docker Desktop
Write-Host "Building Docker image..."
docker.exe build -f apps/api/Dockerfile -t 911229172121.dkr.ecr.us-east-1.amazonaws.com/bank-statement-api:latest .
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

# Push the docker image
Write-Host "Pushing Docker image..."
docker.exe push 911229172121.dkr.ecr.us-east-1.amazonaws.com/bank-statement-api:latest
if ($LASTEXITCODE -ne 0) { throw "Push failed" }

# Update ECS task definition
Write-Host "Updating task definition..."
python.exe -c "
import subprocess, json
result = subprocess.run(['aws.exe', 'ecs', 'describe-task-definition', '--task-definition', 'bank-statement-api', '--query', 'taskDefinition', '--output', 'json'], capture_output=True, text=True, check=True)
td = json.loads(result.stdout)
keep = ['family', 'taskRoleArn', 'executionRoleArn', 'networkMode', 'containerDefinitions', 'requiresCompatibilities', 'cpu', 'memory', 'runtimePlatform']
new_td = {k: td[k] for k in keep if k in td}
new_td['containerDefinitions'][0]['image'] = '911229172121.dkr.ecr.us-east-1.amazonaws.com/bank-statement-api:latest'
with open('api_td_latest.json', 'w') as f:
    json.dump(new_td, f)
"

# Register new task
Write-Host "Registering task..."
$API_ARN = (aws.exe ecs register-task-definition --cli-input-json file://api_td_latest.json --query `"taskDefinition.taskDefinitionArn`" --output text).Trim()

# Update service
Write-Host "Deploying service with ARN $API_ARN"
aws.exe ecs update-service --cluster bank-statement-cluster --service bank-statement-api-service --task-definition $API_ARN --force-new-deployment | Out-Null

Write-Host "DEPLOYMENT FINISHED SUCCESSFULLY!"
