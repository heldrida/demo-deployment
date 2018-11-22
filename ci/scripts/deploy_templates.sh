#!/usr/bin/env bash

# Check if ci/templates/*.template should be deployed
# But not the ci/templates/targetgroup.template since it will always be deployed
# --diff-filter=CopiedAddedRenamedModified to exclude removed templates
# --full-index show full image blob names
# HEAD^..HEAD will only display the previous parent to the current one
changedTemplates=$(git log --diff-filter=CARM --name-only --pretty=oneline --full-index HEAD^..HEAD | grep -vE '^[0-9a-f]{40} ' | sort | uniq | grep "^ci/templates" | grep -v "ci/templates/targetgroup.template")

# If no changes in ci/templates/, exit early
if [ -z "$changedTemplates" ]; then
  echo "No changes in found ci/templates/"
  exit 0
fi

# Check environment and set StackEnv based on it. Only prod gets Datadog.
if [ "$ENVIRONMENT" == "prod" ]; then
  STACKENV="PROD"
elif [ "$ENVIRONMENT" == "test" ]; then
  STACKENV="UAT"
else
  STACKENV="OTHER"
fi

put_secrets_in_parameter_store(){
  aws ssm put-parameter --overwrite --type "String" --name "/${ENVIRONMENT}-cluster/${IMAGE_NAME}/DBNAME" --value "${DBNAME}"
  aws ssm put-parameter --overwrite --type "SecureString" --name "/${ENVIRONMENT}-cluster/${IMAGE_NAME}/DBPASSWORD" --value "${DBPASSWORD}"
  aws ssm put-parameter --overwrite --type "String" --name "/${ENVIRONMENT}-cluster/${IMAGE_NAME}/DBHOST" --value "${DBHOST}"
  aws ssm put-parameter --overwrite --type "String" --name "/${ENVIRONMENT}-cluster/${IMAGE_NAME}/DBUSER" --value "${DBUSER}"
}

echo "Following changes found in ci/templates/"
echo $changedTemplates

echo "Deploying templates..."
for template in $changedTemplates
do

  # Remove path ci/templates and extension .template to get the templateName
  templateName=$(basename $template .template)

  # Create the StackName
  stackName="${IMAGE_NAME}-${ENVIRONMENT}-${templateName}"

  # Deploy the cloudformation templates
  # Set default parameters based on Environment
  aws cloudformation deploy \
  --capabilities CAPABILITY_IAM \
  --template-file $template \
  --stack-name $stackName \
  --parameter-overrides \
  AlbStack="${ENVIRONMENT}-alb" \
  EcsStack="${ENVIRONMENT}-cluster" \
  EncryptLambdaStack="cfn-encrypt" \
  DatadogStack="cfn-datadog" \
  NetworkStack="aws-gotamedia-${ENVIRONMENT}-vpc" \
  StackEnv=$STACKENV \
  DbPassword=$DBPASSWORD \
  DbName=$DBNAME \
  DbMasterUser=$DBUSER

  # Deployment summary
  ci/scripts/aws-cloudformation-stack-status.sh --region $AWS_DEFAULT_REGION --stack-name $stackName

  # Get outputs and export them
  echo "Getting Exports from ${template}..."
  stackId=$(aws cloudformation describe-stacks --query "Stacks[?StackName=='${stackName}']".StackId --output text)
  jsonExports=$(aws cloudformation list-exports --query "Exports[?ExportingStackId=='${stackId}'].[Name, Value]")

  # Export each output name and value as an environment variable
  # First output each record as Table Separated Values (@tsv)
  echo $jsonExports | jq -r ".[] | @tsv" |
    # Separate values on tab (\t)
    # Set first column to $exportName and second column to $exportValue
    while IFS=$'\t' read -r exportName exportValue; do
     # Export each output
     # Replace - with _ using shell replacement (//-/_)
     echo ${exportName//-/_}=${exportValue}

     # Set DB configuration with variables from exports if rds template is detected
     if [ "$templateName" == "rds" ]; then
       # Make sure the name of the exported variable is DBHOST for the rds URI
       exportName=DBHOST
       export ${exportName}=${exportValue}
     else
       export ${exportName//-/_}=${exportValue}
     fi
     # Put secrets in the parameter store to be used in update_task.sh
     put_secrets_in_parameter_store
     done
done

