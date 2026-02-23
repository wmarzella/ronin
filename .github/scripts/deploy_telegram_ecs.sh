#!/usr/bin/env bash
set -euo pipefail

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd aws
require_cmd jq
require_cmd docker

AWS_REGION="${AWS_REGION:-us-east-1}"
NAME_PREFIX="${NAME_PREFIX:-ronin}"

ECR_REPOSITORY="${ECR_REPOSITORY:-${NAME_PREFIX}-worker}"
ECS_CLUSTER="${ECS_CLUSTER:-${NAME_PREFIX}-worker}"
BASE_TASK_FAMILY="${BASE_TASK_FAMILY:-${NAME_PREFIX}-worker}"
TELEGRAM_TASK_FAMILY="${TELEGRAM_TASK_FAMILY:-${NAME_PREFIX}-telegram-bot}"
TELEGRAM_SERVICE_NAME="${TELEGRAM_SERVICE_NAME:-${NAME_PREFIX}-telegram-bot}"
WORKER_GMAIL_RULE="${WORKER_GMAIL_RULE:-${NAME_PREFIX}-worker-gmail}"
WORKER_DRIFT_RULE="${WORKER_DRIFT_RULE:-${NAME_PREFIX}-worker-drift}"

TELEGRAM_BOT_TOKEN_REF="${TELEGRAM_BOT_TOKEN_REF:-/ronin/telegram/bot_token}"
TELEGRAM_CHAT_ID_REF="${TELEGRAM_CHAT_ID_REF:-/ronin/telegram/chat_id}"

SUBNET_IDS="${SUBNET_IDS:-}"
SECURITY_GROUP_IDS="${SECURITY_GROUP_IDS:-}"
ASSIGN_PUBLIC_IP="${ASSIGN_PUBLIC_IP:-ENABLED}"
CONTAINER_NAME="${CONTAINER_NAME:-ronin-telegram}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORM="${PLATFORM:-linux/amd64}"
DESIRED_COUNT="${DESIRED_COUNT:-1}"

export AWS_REGION

echo "Resolving AWS account/ECR..."
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query 'Account' --output text)"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}"

if ! aws ecr describe-repositories --repository-names "${ECR_REPOSITORY}" >/dev/null 2>&1; then
  echo "ECR repository ${ECR_REPOSITORY} does not exist." >&2
  exit 1
fi

echo "Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Building and pushing image ${ECR_URI}..."
docker buildx build --platform "${PLATFORM}" -t "${ECR_URI}" --push .

resolve_secret_ref() {
  local ref="$1"
  if [[ -z "${ref}" ]]; then
    echo "Empty secret reference." >&2
    return 1
  fi

  if [[ "${ref}" == arn:aws:ssm:* ]] || [[ "${ref}" == arn:aws:secretsmanager:* ]]; then
    echo "${ref}"
    return 0
  fi

  if aws ssm get-parameter --name "${ref}" --with-decryption --query 'Parameter.Value' --output text >/dev/null 2>&1; then
    aws ssm get-parameter --name "${ref}" --query 'Parameter.ARN' --output text
    return 0
  fi

  if aws secretsmanager get-secret-value --secret-id "${ref}" --query 'SecretString' --output text >/dev/null 2>&1; then
    aws secretsmanager describe-secret --secret-id "${ref}" --query 'ARN' --output text
    return 0
  fi

  echo "Unable to resolve secret reference: ${ref}" >&2
  return 1
}

resolve_network_from_rule() {
  local rule_name="$1"
  local raw_json
  raw_json="$(
    aws events list-targets-by-rule \
      --rule "${rule_name}" \
      --query 'Targets[0].EcsParameters.NetworkConfiguration.awsvpcConfiguration' \
      --output json 2>/dev/null || true
  )"

  if network_json_is_empty "${raw_json}"; then
    echo "${raw_json}"
    return 0
  fi

  jq -c \
    '{subnets:(.subnets // .Subnets // []), securityGroups:(.securityGroups // .SecurityGroups // []), assignPublicIp:(.assignPublicIp // .AssignPublicIp // "ENABLED")}' \
    <<<"${raw_json}"
}

network_json_is_empty() {
  local value="${1:-}"
  [[ -z "${value}" || "${value}" == "null" || "${value}" == "{}" || "${value}" == "None" ]]
}

echo "Resolving Telegram secret references via AWS CLI..."
TELEGRAM_BOT_TOKEN_ARN="$(resolve_secret_ref "${TELEGRAM_BOT_TOKEN_REF}")"
TELEGRAM_CHAT_ID_ARN="$(resolve_secret_ref "${TELEGRAM_CHAT_ID_REF}")"

echo "Loading base ECS task definition ${BASE_TASK_FAMILY}..."
BASE_TASK_JSON="$(aws ecs describe-task-definition --task-definition "${BASE_TASK_FAMILY}" --query 'taskDefinition' --output json)"

CPU="$(jq -r '.cpu' <<<"${BASE_TASK_JSON}")"
MEMORY="$(jq -r '.memory' <<<"${BASE_TASK_JSON}")"
NETWORK_MODE="$(jq -r '.networkMode' <<<"${BASE_TASK_JSON}")"
EXEC_ROLE_ARN="$(jq -r '.executionRoleArn // ""' <<<"${BASE_TASK_JSON}")"
TASK_ROLE_ARN="$(jq -r '.taskRoleArn // ""' <<<"${BASE_TASK_JSON}")"
REQUIRES_COMPATIBILITIES="$(jq -c '.requiresCompatibilities // ["FARGATE"]' <<<"${BASE_TASK_JSON}")"
LOG_CONFIGURATION="$(jq -c '.containerDefinitions[0].logConfiguration // {}' <<<"${BASE_TASK_JSON}")"
BASE_ENVIRONMENT="$(jq -c '.containerDefinitions[0].environment // []' <<<"${BASE_TASK_JSON}")"
BASE_SECRETS="$(jq -c '.containerDefinitions[0].secrets // []' <<<"${BASE_TASK_JSON}")"
RUNTIME_PLATFORM="$(jq -c '.runtimePlatform // null' <<<"${BASE_TASK_JSON}")"
EPHEMERAL_STORAGE="$(jq -c '.ephemeralStorage // null' <<<"${BASE_TASK_JSON}")"

ENVIRONMENT_JSON="$(
  jq -cn \
    --argjson base "${BASE_ENVIRONMENT}" \
    '$base + [{"name":"RONIN_DB_BACKEND","value":"postgres"}]
    | group_by(.name)
    | map(.[-1])'
)"

TELEGRAM_SECRETS="$(
  jq -cn \
    --arg token "${TELEGRAM_BOT_TOKEN_ARN}" \
    --arg chat "${TELEGRAM_CHAT_ID_ARN}" \
    '[
      {"name":"RONIN_TELEGRAM_BOT_TOKEN","valueFrom":$token},
      {"name":"RONIN_TELEGRAM_CHAT_ID","valueFrom":$chat}
    ]'
)"

SECRETS_JSON="$(
  jq -cn \
    --argjson base "${BASE_SECRETS}" \
    --argjson tg "${TELEGRAM_SECRETS}" \
    '$base + $tg
    | group_by(.name)
    | map(.[-1])'
)"

TASKDEF_JSON="$(
  jq -cn \
    --arg family "${TELEGRAM_TASK_FAMILY}" \
    --arg network_mode "${NETWORK_MODE}" \
    --arg cpu "${CPU}" \
    --arg memory "${MEMORY}" \
    --arg execution_role_arn "${EXEC_ROLE_ARN}" \
    --arg task_role_arn "${TASK_ROLE_ARN}" \
    --arg container_name "${CONTAINER_NAME}" \
    --arg image "${ECR_URI}" \
    --argjson requires_compatibilities "${REQUIRES_COMPATIBILITIES}" \
    --argjson log_configuration "${LOG_CONFIGURATION}" \
    --argjson environment "${ENVIRONMENT_JSON}" \
    --argjson secrets "${SECRETS_JSON}" \
    --argjson runtime_platform "${RUNTIME_PLATFORM}" \
    --argjson ephemeral_storage "${EPHEMERAL_STORAGE}" \
    '
    {
      family: $family,
      networkMode: $network_mode,
      requiresCompatibilities: $requires_compatibilities,
      cpu: $cpu,
      memory: $memory,
      executionRoleArn: $execution_role_arn,
      taskRoleArn: $task_role_arn,
      containerDefinitions: [
        {
          name: $container_name,
          image: $image,
          essential: true,
          command: ["telegram", "bot"],
          environment: $environment,
          secrets: $secrets,
          logConfiguration: $log_configuration
        }
      ],
      runtimePlatform: $runtime_platform,
      ephemeralStorage: $ephemeral_storage
    }
    | if .executionRoleArn == "" then del(.executionRoleArn) else . end
    | if .taskRoleArn == "" then del(.taskRoleArn) else . end
    | if .runtimePlatform == null then del(.runtimePlatform) else . end
    | if .ephemeralStorage == null then del(.ephemeralStorage) else . end
    '
)"

TASKDEF_FILE="$(mktemp)"
printf '%s\n' "${TASKDEF_JSON}" >"${TASKDEF_FILE}"

echo "Registering task definition ${TELEGRAM_TASK_FAMILY}..."
TASKDEF_ARN="$(
  aws ecs register-task-definition \
    --cli-input-json "file://${TASKDEF_FILE}" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text
)"

rm -f "${TASKDEF_FILE}"

echo "Resolving network config..."
SERVICE_INFO="$(aws ecs describe-services --cluster "${ECS_CLUSTER}" --services "${TELEGRAM_SERVICE_NAME}" --output json)"
SERVICE_EXISTS="$(jq -r '.services[0].status // "MISSING"' <<<"${SERVICE_INFO}")"

NETWORK_JSON="{}"
if [[ "${SERVICE_EXISTS}" != "MISSING" ]]; then
  NETWORK_JSON="$(jq -c '.services[0].networkConfiguration.awsvpcConfiguration' <<<"${SERVICE_INFO}")"
fi

if network_json_is_empty "${NETWORK_JSON}"; then
  NETWORK_JSON="$(resolve_network_from_rule "${WORKER_GMAIL_RULE}")"
fi

if network_json_is_empty "${NETWORK_JSON}"; then
  NETWORK_JSON="$(resolve_network_from_rule "${WORKER_DRIFT_RULE}")"
fi

if network_json_is_empty "${NETWORK_JSON}"; then
  if [[ -z "${SUBNET_IDS}" || -z "${SECURITY_GROUP_IDS}" ]]; then
    echo "Unable to auto-resolve subnet/security group. Set SUBNET_IDS and SECURITY_GROUP_IDS." >&2
    exit 1
  fi

  SUBNETS_JSON="$(jq -cn --arg csv "${SUBNET_IDS}" '$csv | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(length>0))')"
  SGS_JSON="$(jq -cn --arg csv "${SECURITY_GROUP_IDS}" '$csv | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(length>0))')"
  NETWORK_JSON="$(
    jq -cn \
      --argjson subnets "${SUBNETS_JSON}" \
      --argjson sgs "${SGS_JSON}" \
      --arg assign_public_ip "${ASSIGN_PUBLIC_IP}" \
      '{subnets:$subnets, securityGroups:$sgs, assignPublicIp:$assign_public_ip}'
  )"
fi

SUBNETS_JSON="$(jq -c '.subnets // []' <<<"${NETWORK_JSON}")"
SGS_JSON="$(jq -c '.securityGroups // []' <<<"${NETWORK_JSON}")"
ASSIGN_PUBLIC_IP_VALUE="$(jq -r '.assignPublicIp // "ENABLED"' <<<"${NETWORK_JSON}")"

if [[ "$(jq 'length' <<<"${SUBNETS_JSON}")" -eq 0 ]]; then
  if [[ -n "${SUBNET_IDS}" ]]; then
    SUBNETS_JSON="$(jq -cn --arg csv "${SUBNET_IDS}" '$csv | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(length>0))')"
  else
    echo "No subnets resolved for ECS service." >&2
    exit 1
  fi
fi

if [[ "$(jq 'length' <<<"${SGS_JSON}")" -eq 0 ]]; then
  if [[ -n "${SECURITY_GROUP_IDS}" ]]; then
    SGS_JSON="$(jq -cn --arg csv "${SECURITY_GROUP_IDS}" '$csv | split(",") | map(gsub("^\\s+|\\s+$";"")) | map(select(length>0))')"
  else
    echo "No security groups resolved for ECS service." >&2
    exit 1
  fi
fi

NETWORK_CONFIG_JSON="$(
  jq -cn \
    --argjson subnets "${SUBNETS_JSON}" \
    --argjson sgs "${SGS_JSON}" \
    --arg assign_public_ip "${ASSIGN_PUBLIC_IP_VALUE}" \
    '{awsvpcConfiguration:{subnets:$subnets,securityGroups:$sgs,assignPublicIp:$assign_public_ip}}'
)"

if [[ "${SERVICE_EXISTS}" == "ACTIVE" ]]; then
  echo "Updating ECS service ${TELEGRAM_SERVICE_NAME}..."
  aws ecs update-service \
    --cluster "${ECS_CLUSTER}" \
    --service "${TELEGRAM_SERVICE_NAME}" \
    --task-definition "${TASKDEF_ARN}" \
    --desired-count "${DESIRED_COUNT}" \
    --force-new-deployment >/dev/null
else
  echo "Creating ECS service ${TELEGRAM_SERVICE_NAME}..."
  aws ecs create-service \
    --cluster "${ECS_CLUSTER}" \
    --service-name "${TELEGRAM_SERVICE_NAME}" \
    --task-definition "${TASKDEF_ARN}" \
    --desired-count "${DESIRED_COUNT}" \
    --launch-type FARGATE \
    --platform-version LATEST \
    --network-configuration "${NETWORK_CONFIG_JSON}" >/dev/null
fi

echo "Waiting for ECS service to stabilize..."
aws ecs wait services-stable --cluster "${ECS_CLUSTER}" --services "${TELEGRAM_SERVICE_NAME}"
echo "Deployment complete."
