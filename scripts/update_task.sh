#!/bin/bash

set -eufx

make_task_def(){
    set -e
	cp deployments/$TASK_NAME.json deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
	sed -i "s/AWS_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
	#sed -i "s/BITBUCKET_COMMIT/${BITBUCKET_COMMIT}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
	sed -i "s/AWS_DEFAULT_REGION/${AWS_DEFAULT_REGION}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s/ENVIRONMENT/${ENVIRONMENT}/g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|IMAGE_NAME|${IMAGE_NAME}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|SUMO_URL|${SUMO_URL}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|SUMO_CATEGORY|${SUMO_CATEGORY}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
    sed -i "s|DOCKERTAG|${DOCKERTAG}|g" deployments/$TASK_NAME-$BITBUCKET_COMMIT.json
}
make_task_def
echo "Deploying from deployments/$TASK_NAME-$BITBUCKET_COMMIT.json"
rev=$(aws ecs register-task-definition --cli-input-json file://deployments/$TASK_NAME-$BITBUCKET_COMMIT.json |  jq '.taskDefinition.revision')
echo "New revision $TASK_NAME-$rev created"

serv=$(aws ecs update-service --cluster ${ECS_CLUSTER} --service $TASK_NAME --force-new-deployment --task-definition $TASK_NAME:$rev | jq '.service.taskDefinition')
echo $serv

aws ecs wait services-stable --cluster ${ECS_CLUSTER} --services $TASK_NAME
echo "Service is stable, deployment successful"