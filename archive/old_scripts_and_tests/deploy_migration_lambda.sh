#!/bin/bash
set -e

echo "Deploying updated db-migration Lambda with behavior learning migration..."
echo

cd services/db_migration_lambda

echo "1. Creating deployment package..."
rm -f migration_lambda.zip
cd package
zip -r ../migration_lambda.zip . > /dev/null
cd ..
zip -g migration_lambda.zip lambda_function.py

echo "2. Updating Lambda function..."
aws lambda update-function-code \
  --function-name ops-pipeline-db-migration \
  --zip-file fileb://migration_lambda.zip \
  --region us-west-2

echo
echo "✅ Lambda updated successfully!"
echo
echo "Next step: Run the migration"
echo "  python3 ../../apply_behavior_learning_migration.py"
