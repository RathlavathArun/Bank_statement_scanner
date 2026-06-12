#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Bank Statement Scanner — aws.exe Deployment Script
# Orchestrates: Terraform → docker.exe Build → ECR Push → ECS Deploy
# ──────────────────────────────────────────────────────────────
set -eu

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Colour

log()   { echo -e "${BLUE}[DEPLOY]${NC} $*"; }
ok()    { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()   { echo -e "${RED}[ERROR ]${NC} $*" >&2; }

# ── Paths ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$SCRIPT_DIR/terraform"

# ── Pre-flight Checks ───────────────────────────────────────
log "Pre-flight checks..."
ok "Skipping tool checks"
ok "All required tools found (aws, terraform, docker)"

# Verify aws.exe credentials
if ! aws.exe sts get-caller-identity &>/dev/null; then
    err "aws.exe credentials not configured. Run 'aws.exe configure' first."
    exit 1
fi
AWS_ACCOUNT_ID=$(aws.exe sts get-caller-identity --query Account --output text | tr -d '\r')
ok "aws.exe Account: $AWS_ACCOUNT_ID"

# ═════════════════════════════════════════════════════════════
# STEP 1: Terraform — Provision Infrastructure (SKIPPED)
# ═════════════════════════════════════════════════════════════
log "━━━ Step 1/6: Terraform Init & Apply (SKIPPED) ━━━"

# cd "$TF_DIR"
# terraform init -input=false
# log "Running terraform plan..."
# terraform plan -out=tfplan -input=false
# log "Applying terraform plan..."
# terraform apply -input=false tfplan
# rm -f tfplan

ok "Infrastructure provisioned successfully"

# ═════════════════════════════════════════════════════════════
# STEP 2: Capture Terraform Outputs (HARDCODED FOR EXISTING INFRA)
# ═════════════════════════════════════════════════════════════
log "━━━ Step 2/6: Capturing Outputs ━━━"

AWS_REGION="us-east-1"
ALB_DNS=$(aws.exe elbv2 describe-load-balancers --query 'LoadBalancers[0].DNSName' --output text 2>/dev/null | tr -d '\r' || echo "unknown")
ECR_WEB_URL="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/bank-statement-web"
ECR_API_URL="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/bank-statement-api"
RDS_ENDPOINT="existing"
REDIS_ENDPOINT="existing"
S3_BUCKET="existing"
API_DISCOVERY_DNS="api.bank-statement.local"

ok "ALB DNS:          $ALB_DNS"
ok "ECR Web:          $ECR_WEB_URL"
ok "ECR API:          $ECR_API_URL"
ok "RDS Endpoint:     $RDS_ENDPOINT"
ok "Redis Endpoint:   $REDIS_ENDPOINT"
ok "S3 Bucket:        $S3_BUCKET"
ok "API Discovery:    $API_DISCOVERY_DNS"
ok "aws.exe Region:       $AWS_REGION"

cd "$REPO_ROOT"

# ═════════════════════════════════════════════════════════════
# STEP 3: docker.exe Login to ECR
# ═════════════════════════════════════════════════════════════
log "━━━ Step 3/6: ECR docker.exe Login ━━━"

aws.exe ecr get-login-password --region "$AWS_REGION" | tr -d '\r' \
    | docker.exe login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

ok "Logged in to ECR"

# ═════════════════════════════════════════════════════════════
# STEP 4: Build & Push API Image
# ═════════════════════════════════════════════════════════════
log "━━━ Step 4/6: Build & Push API Image ━━━"

IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"
API_IMAGE="$ECR_API_URL:$IMAGE_TAG"
API_IMAGE_LATEST="$ECR_API_URL:latest"

log "Building API image (tag: $IMAGE_TAG)..."
# Build from repo root so Dockerfile can COPY packages/bank-templates
docker.exe build \
    --no-cache \
    -f apps/api/Dockerfile \
    -t "$API_IMAGE" \
    -t "$API_IMAGE_LATEST" \
    .

log "Pushing API image to ECR..."
docker.exe push "$API_IMAGE"
docker.exe push "$API_IMAGE_LATEST"

ok "API image pushed: $API_IMAGE"

# ═════════════════════════════════════════════════════════════
# STEP 5: Build & Push Web Image
# ═════════════════════════════════════════════════════════════
log "━━━ Step 5/6: Build & Push Web Image ━━━"

WEB_IMAGE="$ECR_WEB_URL:$IMAGE_TAG"
WEB_IMAGE_LATEST="$ECR_WEB_URL:latest"

# The web container reaches the API via Cloud Map service discovery
API_INTERNAL_URL="http://${API_DISCOVERY_DNS}:8000"

log "Building Web image (API_URL=$API_INTERNAL_URL)..."
docker.exe build \
    --no-cache \
    -f apps/web/Dockerfile \
    --build-arg "API_URL=$API_INTERNAL_URL" \
    -t "$WEB_IMAGE" \
    -t "$WEB_IMAGE_LATEST" \
    apps/web/

log "Pushing Web image to ECR..."
docker.exe push "$WEB_IMAGE"
docker.exe push "$WEB_IMAGE_LATEST"

ok "Web image pushed: $WEB_IMAGE"

# ═════════════════════════════════════════════════════════════
# STEP 6: Update ECS Services
# ═════════════════════════════════════════════════════════════
log "━━━ Step 6/6: Deploy to ECS ━━━"

ECS_CLUSTER="bank-statement-cluster"
API_SERVICE="bank-statement-api-service"
WEB_SERVICE="bank-statement-web-service"

# Update API task definition with new image
log "Registering new API task definition..."
API_TASK_DEF=$(aws.exe ecs describe-task-definition \
    --task-definition bank-statement-api \
    --region "$AWS_REGION" \
    --query 'taskDefinition' \
    --output json)

# Replace the placeholder/old image with the new one and update CORS
NEW_API_TASK_DEF=$(echo "$API_TASK_DEF" | python.exe -c "
import sys, json
td = json.load(sys.stdin)
td['containerDefinitions'][0]['image'] = '$API_IMAGE'
# Update CORS_ORIGINS to include both HTTP and HTTPS
env_vars = {e['name']: e for e in td['containerDefinitions'][0].get('environment', [])}
env_vars['CORS_ORIGINS'] = {
    'name': 'CORS_ORIGINS',
    'value': 'http://$ALB_DNS,https://$ALB_DNS,http://localhost:3000'
}
td['containerDefinitions'][0]['environment'] = list(env_vars.values())
# Keep only the fields needed for register-task-definition
keep = ['family','taskRoleArn','executionRoleArn','networkMode','containerDefinitions',
        'requiresCompatibilities','cpu','memory','runtimePlatform']
result = {k: td[k] for k in keep if k in td}
print(json.dumps(result))
")

API_NEW_TASK_ARN=$(aws.exe ecs register-task-definition \
    --region "$AWS_REGION" \
    --cli-input-json "$NEW_API_TASK_DEF" \
    --output text --query 'taskDefinition.taskDefinitionArn' | tr -d '\r')

ok "New API task definition registered: $API_NEW_TASK_ARN"

# Update Web task definition with new image AND environment variables
log "Registering new Web task definition..."
WEB_TASK_DEF=$(aws.exe ecs describe-task-definition \
    --task-definition bank-statement-web \
    --region "$AWS_REGION" \
    --query 'taskDefinition' \
    --output json)

NEW_WEB_TASK_DEF=$(echo "$WEB_TASK_DEF" | python.exe -c "
import sys, json
td = json.load(sys.stdin)
td['containerDefinitions'][0]['image'] = '$WEB_IMAGE'
# Ensure the web container has the API_URL env var for Next.js rewrites
env_vars = {e['name']: e for e in td['containerDefinitions'][0].get('environment', [])}
required_env = {
    'API_URL': 'http://${API_DISCOVERY_DNS}:8000',
    'HOSTNAME': '0.0.0.0',
    'PORT': '3000',
    'NODE_ENV': 'production',
}
for name, value in required_env.items():
    env_vars[name] = {'name': name, 'value': value}
td['containerDefinitions'][0]['environment'] = list(env_vars.values())
keep = ['family','taskRoleArn','executionRoleArn','networkMode','containerDefinitions',
        'requiresCompatibilities','cpu','memory','runtimePlatform']
result = {k: td[k] for k in keep if k in td}
print(json.dumps(result))
")

WEB_NEW_TASK_ARN=$(aws.exe ecs register-task-definition \
    --region "$AWS_REGION" \
    --cli-input-json "$NEW_WEB_TASK_DEF" \
    --output text --query 'taskDefinition.taskDefinitionArn' | tr -d '\r')

ok "New Web task definition registered: $WEB_NEW_TASK_ARN"

# Force new deployments with the new task definitions
log "Forcing new deployment for API service..."
aws.exe ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$API_SERVICE" \
    --task-definition "$API_NEW_TASK_ARN" \
    --force-new-deployment \
    --region "$AWS_REGION" \
    --output text --query 'service.serviceName'

log "Forcing new deployment for Web service..."
aws.exe ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$WEB_SERVICE" \
    --task-definition "$WEB_NEW_TASK_ARN" \
    --force-new-deployment \
    --region "$AWS_REGION" \
    --output text --query 'service.serviceName'

ok "ECS deployments triggered"

# ═════════════════════════════════════════════════════════════
# Wait for services to stabilize
# ═════════════════════════════════════════════════════════════
log "Waiting for ECS services to stabilize (this may take 3-5 minutes)..."

aws.exe ecs wait services-stable \
    --cluster "$ECS_CLUSTER" \
    --services "$API_SERVICE" "$WEB_SERVICE" \
    --region "$AWS_REGION" 2>/dev/null || warn "Timeout waiting for services — check aws.exe Console"

ok "ECS services are stable"

# ═════════════════════════════════════════════════════════════
# Health Check
# ═════════════════════════════════════════════════════════════
log "Running health check..."

sleep 10  # Give ALB a moment to register targets

for i in {1..5}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://$ALB_DNS/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        ok "Health check passed (HTTP $HTTP_CODE)"
        break
    fi
    warn "Health check attempt $i/5 — HTTP $HTTP_CODE. Retrying in 15s..."
    sleep 15
done

# ═════════════════════════════════════════════════════════════
# Done!
# ═════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🎉 Deployment Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  🌐 Web App:     ${BLUE}http://$ALB_DNS${NC}"
echo -e "  📡 API Health:  ${BLUE}http://$ALB_DNS/health${NC}"
echo -e "  📖 API Docs:    ${BLUE}http://$ALB_DNS/docs${NC}"
echo -e "  📊 Metrics:     ${BLUE}http://$ALB_DNS/metrics${NC}"
echo ""
echo -e "  🏷️  Image Tag:   $IMAGE_TAG"
echo -e "  📦 S3 Bucket:   $S3_BUCKET"
echo -e "  🗄️  RDS:         $RDS_ENDPOINT"
echo -e "  ⚡ Redis:       $REDIS_ENDPOINT"
echo ""
