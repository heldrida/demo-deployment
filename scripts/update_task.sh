#!/bin/bash

set -eufx

make_task_def(){
    set -e
	cp deployments/$TASK_NAME.json deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
	sed -i "s/AWS_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
	#sed -i "s/BITBUCKET_COMMIT/${BITBUCKET_COMMIT}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
	sed -i "s/AWS_DEFAULT_REGION/${AWS_DEFAULT_REGION}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s/ENVIRONMENT/${ENVIRONMENT}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|DOCKER_IMAGE|${DOCKER_IMAGE}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|SUMO_URL|${SUMO_URL}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|SUMO_CATEGORY|${SUMO_CATEGORY}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|TASK_NAME|${TASK_NAME}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
}
make_task_def
echo "Deploying from deployments/$TASK_NAME-$BITBUCKET_COMMIT.json"
rev=$(aws ecs register-task-definition --cli-input-json file://deployments/$TASK_NAME-$BITBUCKET_COMMIT.json |  jq '.taskDefinition.revision')
echo "New revision $TASK_NAME-$rev created"

# Update the service with a new deployment of a task-definition
#serv=$(aws ecs update-service --cluster ${ECS_CLUSTER} --service $TASK_NAME --force-new-deployment --task-definition $TASK_NAME:$rev | jq '.service.taskDefinition')
#echo $serv

# Deploy or update a cloudformation template with the new task-definition and force a new deployment of the service
# Parameters
#  HealthCheckPath
#  AutoscalingMax
#  AutoscalingMin
#  ServicePath # OR #  ServiceHost
#  ListenerPriority # Default: 10 #
#  ContainerName  # Publically accessable container in task definition #
#  ContainerPort
#  AlbStack  #  dev-alb #
#  EcsStack  #  dev-cluster #
#  EncryptLambdaStack  #  cfn-encrypt #
#  DatadogStack  #  cfn-datadog #
#  NetworkStack  #  aws-gotamedia-dev-vpc #
#  CertificateArn  # Not needed #
#  StackEnv  # PROD, UAT, OTHER #
#  TaskDefinition  # ARN of the TaskDefintion created/updated above with this script arn:aws:ecs:eu-west-1:145601632047:task-definition/$TASK_NAME-$rev #

echo "Deploying service with Cloudformation"
# Get the ARN of the taskdefinition
taskDefinitionArn=$(aws ecs describe-task-definition --task-definition $TASK_NAME:$rev | jq '.taskDefinition.taskDefinitionArn')
echo $taskDefinitionArn

# Deploy with cloudformation
aws cloudformation deploy --template-file demo-targetgroup.template \
 --stack-name $TASK_NAME \
 --parameter-overrides \
  HealthCheckPath="/" \
  AutoscalingMax=3 \
  AutoscalingMin=3 \
  ServicePath="/" \
  ServiceHost="NONE" \
  ListenerPriority=10 \
  ContainerName="simple-app" \
  ContainerPort=80 \
  EcsStack=dev-cluster \
  EncryptLambdaStack=cfn-encrypt \
  DatadogStack=cfn-datadog \
  NetworkStack=aws-gotamedia-dev-vpc \
  CertificateArn="NONE" \
  StackEnv="OTHER" \
  TaskDefinition=$taskDefinitionArn

aws ecs wait services-stable --cluster ${ECS_CLUSTER} --services $TASK_NAME
echo "Service is stable, deployment successful"