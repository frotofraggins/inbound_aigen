#!/usr/bin/env python3
"""
Apply migration 013 via Lambda
Adds peak_price and trailing_stop_price columns for trailing stops feature
"""
import boto3
import json

def create_and_invoke_lambda():
    """Create Lambda function code and invoke it"""
    
    # Lambda function code
    lambda_code = """
import json
import boto3
import psycopg2

def lambda_handler(event, context):
    '''Apply migration 013 to add trailing stops columns'''
    
    # Get database credentials
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    db_secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(db_secret['SecretString'])
    
    ssm = boto3.client('ssm', region_name='us-west-2')
    response = ssm.get_parameters_by_path(
        Path='/ops-pipeline/db',
        WithDecryption=True
    )
    
    param_dict = {}
    for param in response['Parameters']:
        key = param['Name'].split('/')[-1]
        param_dict[key] = param['Value']
    
    # Connect to database
    conn = psycopg2.connect(
        host=param_dict.get('host', param_dict.get('endpoint', '')),
        port=int(param_dict.get('port', 5432)),
        dbname=param_dict.get('name', param_dict.get('database', '')),
        user=secret_data['username'],
        password=secret_data['password']
    )
    
    migration_sql = '''
    BEGIN;
    
    -- Add columns for trailing stop support
    ALTER TABLE active_positions 
    ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
    ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4),
    ADD COLUMN IF NOT EXISTS entry_underlying_price DECIMAL(12, 4),
    ADD COLUMN IF NOT EXISTS original_quantity INTEGER;
    
    -- Add IV rank tracking to ticker_features
    ALTER TABLE ticker_features_1m
    ADD COLUMN IF NOT EXISTS iv_rank DECIMAL(5, 4);
    
    -- Create IV history table for IV rank calculations
    CREATE TABLE IF NOT EXISTS iv_history (
        id SERIAL PRIMARY KEY,
        ticker VARCHAR(10) NOT NULL,
        implied_volatility DECIMAL(8, 6),
        recorded_at TIMESTAMP DEFAULT NOW(),
        
        UNIQUE(ticker, recorded_at)
    );
    
    CREATE INDEX IF NOT EXISTS idx_iv_history_ticker_date 
    ON iv_history(ticker, recorded_at DESC);
    
    -- Add partial exit tracking
    ALTER TABLE position_events
    ADD COLUMN IF NOT EXISTS partial_quantity INTEGER,
    ADD COLUMN IF NOT EXISTS remaining_quantity INTEGER;
    
    COMMIT;
    '''
    
    cur = conn.cursor()
    cur.execute(migration_sql)
    conn.commit()
    cur.close()
    conn.close()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Migration 013 applied successfully',
            'columns_added': [
                'peak_price',
                'trailing_stop_price',
                'entry_underlying_price',
                'original_quantity'
            ]
        })
    }
"""
    
    # Write Lambda code to file
    with open('/tmp/migration_013_lambda.py', 'w') as f:
        f.write(lambda_code)
    
    print("✅ Lambda function code created")
    print("\nInvoking via db-query-lambda...")
    
    # Use existing db-query-lambda to run the SQL
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    
    # Migration SQL
    migration_sql = """
    BEGIN;
    
    ALTER TABLE active_positions 
    ADD COLUMN IF NOT EXISTS peak_price DECIMAL(12, 4),
    ADD COLUMN IF NOT EXISTS trailing_stop_price DECIMAL(12, 4),
    ADD COLUMN IF NOT EXISTS entry_underlying_price DECIMAL(12, 4),
    ADD COLUMN IF NOT EXISTS original_quantity INTEGER;
    
    ALTER TABLE ticker_features_1m
    ADD COLUMN IF NOT EXISTS iv_rank DECIMAL(5, 4);
    
    CREATE TABLE IF NOT EXISTS iv_history (
        id SERIAL PRIMARY KEY,
        ticker VARCHAR(10) NOT NULL,
        implied_volatility DECIMAL(8, 6),
        recorded_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(ticker, recorded_at)
    );
    
    CREATE INDEX IF NOT EXISTS idx_iv_history_ticker_date 
    ON iv_history(ticker, recorded_at DESC);
    
    ALTER TABLE position_events
    ADD COLUMN IF NOT EXISTS partial_quantity INTEGER,
    ADD COLUMN IF NOT EXISTS remaining_quantity INTEGER;
    
    COMMIT;
    """
    
    # ops-pipeline-db-query expects 'sql' key
    payload = {
        'sql': migration_sql
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='ops-pipeline-db-query',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        print("\n✅ Migration 013 applied successfully!")
        print(f"Response: {json.dumps(result, indent=2)}")
        print("\nColumns added:")
        print("  - peak_price")
        print("  - trailing_stop_price")
        print("  - entry_underlying_price")
        print("  - original_quantity")
        print("\nTrailing stops can now be enabled!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error applying migration: {e}")
        print("\nAlternative: Apply via db-migrator ECS task")
        return False

if __name__ == "__main__":
    success = create_and_invoke_lambda()
    if success:
        print("\n🎯 Next step: Enable trailing stops in monitor.py line 394")
    else:
        print("\n⚠️  Migration failed, try db-migrator ECS task instead")
