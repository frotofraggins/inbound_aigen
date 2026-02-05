"""
Lambda function to add missing columns to active_positions table
"""
import json
import boto3
import psycopg2

def lambda_handler(event, context):
    # Get DB credentials
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    secret = secrets.get_secret_value(SecretId='ops-pipeline/db')
    creds = json.loads(secret['SecretString'])
    
    # Get RDS endpoint
    rds = boto3.client('rds', region_name='us-west-2')
    db_instances = rds.describe_db_instances(DBInstanceIdentifier='ops-pipeline-db')
    db_host = db_instances['DBInstances'][0]['Endpoint']['Address']
    
    # Connect to database
    conn = psycopg2.connect(
        host=db_host,
        port=5432,
        dbname='ops_pipeline',
        user=creds['username'],
        password=creds['password']
    )
    
    cur = conn.cursor()
    results = []
    
    # Add original_quantity column
    try:
        cur.execute("""
            ALTER TABLE active_positions 
            ADD COLUMN IF NOT EXISTS original_quantity INTEGER
        """)
        conn.commit()
        results.append("✓ Added original_quantity column")
    except Exception as e:
        results.append(f"original_quantity: {str(e)}")
    
    # Add Phase 3 columns
    for col in ['peak_price', 'trailing_stop_price', 'entry_underlying_price']:
        try:
            cur.execute(f"""
                ALTER TABLE active_positions 
                ADD COLUMN IF NOT EXISTS {col} DECIMAL(12, 4)
            """)
            conn.commit()
            results.append(f"✓ Added {col} column")
        except Exception as e:
            results.append(f"{col}: {str(e)}")
    
    cur.close()
    conn.close()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Migration complete',
            'results': results
        })
    }
