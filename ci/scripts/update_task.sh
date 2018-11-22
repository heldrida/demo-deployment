#!/bin/bash

set -efx

# This function replaces VARIABLES in the task-definition with
# $VARIABLES from the pipeline, such as the image name of the docker image
make_task_def(){
    set -e
    cp ci/task-definitions/$TASK_NAME.json ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s/AWS_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s/AWS_DEFAULT_REGION/${AWS_DEFAULT_REGION}/g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s/ENVIRONMENT/${ENVIRONMENT}/g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|DOCKER_IMAGE|${DOCKER_IMAGE}|g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|SUMO_URL|${SUMO_URL}|g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|SUMO_CATEGORY|${IMAGE_NAME}|g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|TASK_NAME|${TASK_NAME}|g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|CONTAINER_NAME|${TASK_NAME}|g" ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json

}
make_task_def

# Get ARN of ECS cluster role
ecsRole=$(aws cloudformation list-exports --query "Exports[?Name==\`${ENVIRONMENT}-cluster-EcsContainerRole\`].Value" --no-paginate --output text)

# Register a task-definitionand echo the revision
echo "Deploying from ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json"
rev=$(aws ecs register-task-definition --execution-role-arn $ecsRole --cli-input-json file://ci/task-definitions/$TASK_NAME-$BITBUCKET_COMMIT.json |  jq '.taskDefinition.revision')
echo "New revision $TASK_NAME-$rev created"

# Get the ARN of the taskdefinition
taskDefinitionArn=$(aws ecs describe-task-definition --task-definition $TASK_NAME:$rev | jq -r '.taskDefinition.taskDefinitionArn')
echo "Task definition for ${TASK_NAME}:${rev} is: ${taskDefinitionArn}"

# Get ALB public DNS name
albPublicDNS=$(aws cloudformation list-exports --query "Exports[?Name==\`${ENVIRONMENT}-alb-AlbPublicDNSName\`].Value" --no-paginate --output text)

# Get the ARN of the ALB listener
if [ "$CERTIFICATEARN" == "NONE" ]; then
  # Port 80
  albListenerArn=$(aws cloudformation list-exports --query "Exports[?Name==\`${ENVIRONMENT}-alb-AlbPublicListener80\`].Value" --no-paginate --output text)
else
  # Port 443
  albListenerArn=$(aws cloudformation list-exports --query "Exports[?Name==\`${ENVIRONMENT}-alb-AlbPublicListener443\`].Value" --no-paginate --output text)
fi

# Create ALB ListenerPriority by adding +1 to current priority
echo "Retrieving listener rule priority..."
listenerPriority=$(aws elbv2 describe-rules --listener-arn $albListenerArn | jq '[.Rules[].Priority][:-1]' | jq '[.[] | tonumber] | max + 1')
echo "Priority for ${taskDefinitionArn} is: ${listenerPriority}"

# Find out if we're using ServicePath by seeing if the SERVICEPATH variable is set
echo "Checking for ServicePath or ServiceHost"
if [ -z "$SERVICEPATH" ]; then
  echo "Using SERVICEHOST: ${SERVICEHOST}"
  appService="ServiceHost=${SERVICEHOST}"

# If not, use ServicePath instead.
elif [ -z "$SERVICEHOST" ]; then
  echo "Using SERVICEPATH: ${SERVICEPATH}"
  appService="ServicePath=${SERVICEPATH}"

# If both fail, fail the deployment.
else
  echo "Either SERVICEHOST or SERVICEPATH variable must be set"
  echo "See documentation here: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-listeners.html#listener-rules"
  exit 1
fi

# Check environment and set StackEnv based on it. Only prod gets Datadog.
if [ "$ENVIRONMENT" == "prod" ]; then
  STACKENV="PROD"
elif [ "$ENVIRONMENT" == "test" ]; then
  STACKENV="UAT"
else
  STACKENV="OTHER"
fi

deploy_target_group(){
 aws cloudformation deploy \
 --capabilities CAPABILITY_IAM \
 --template-file ci/templates/targetgroup.template \
 --stack-name ${TASK_NAME}-tg \
 --parameter-overrides \
  HealthCheckPath=$HEALTHCHECKPATH \
  AutoscalingMax=$AUTOSCALINGMAX \
  AutoscalingMin=$AUTOSCALINGMIN \
  ListenerPriority=$listenerPriority \
  ContainerName=$IMAGE_NAME \
  ContainerPort=$CONTAINERPORT \
  AlbStack="${ENVIRONMENT}-alb" \
  EcsStack="${ENVIRONMENT}-cluster" \
  EncryptLambdaStack="cfn-encrypt" \
  DatadogStack="cfn-datadog" \
  NetworkStack="aws-gotamedia-${ENVIRONMENT}-vpc" \
  CertificateArn=$CERTIFICATEARN \
  StackEnv=$STACKENV \
  TaskDefinition=$taskDefinitionArn \
  $appService
}

if deploy_target_group; then
  echo "Deployment successful"
  ci/scripts/aws-cloudformation-stack-status.sh --region $AWS_DEFAULT_REGION --stack-name ${TASK_NAME}-tg
else
  echo "Deployment failed, see stack status:"
  ci/scripts/aws-cloudformation-stack-status.sh --region $AWS_DEFAULT_REGION --stack-name ${TASK_NAME}-tg
  exit 1
fi