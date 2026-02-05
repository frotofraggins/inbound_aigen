#!/bin/bash
set -e

echo "Building migration Lambda deployment package..."

# Clean up old zip
rm -f services/db_migration_lambda/migration_lambda.zip

# Create zip from package directory first (dependencies)
cd services/db_migration_lambda/package
zip -r ../migration_lambda.zip . -q
cd ..

# Add lambda function to zip
zip migration_lambda.zip lambda_function.py

cd ../..

echo "Deploying to AWS Lambda..."
aws lambda update-function-code \
  --function-name ops-pipeline-db-migration \
  --zip-file fileb://services/db_migration_lambda/migration_lambda.zip \
  --region us-west-2

echo "Waiting for Lambda to be ready..."
sleep 5

echo "Invoking migration Lambda..."
aws lambda invoke \
  --function-name ops-pipeline-db-migration \
  --region us-west-2 \
  /tmp/migration_result.json

echo ""
echo "Migration result:"
cat /tmp/migration_result.json | python3 -m json.tool

echo ""
echo "Done!"
