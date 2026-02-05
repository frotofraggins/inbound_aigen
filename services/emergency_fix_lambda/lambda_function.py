"""
Emergency Lambda to add missing columns to active_positions
"""
import json
import boto3
import psycopg2

def lambda_handler(event, context):
    # Get config
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    # Connect
    conn = psycopg2.connect(
        host=db_host,
        port=int(db_port),
        database=db_name,
        user=secret_data['username'],
        password=secret_data['password']
    )
    
    cur = conn.cursor()
    results = []
    
    # Add columns
    columns = [
        ('original_quantity', 'INTEGER'),
        ('peak_price', 'DECIMAL(12, 4)'),
        ('trailing_stop_price', 'DECIMAL(12, 4)'),
        ('entry_underlying_price', 'DECIMAL(12, 4)')
    ]
    
    for col_name, col_type in columns:
        try:
            cur.execute(f"""
                ALTER TABLE active_positions 
                ADD COLUMN IF NOT EXISTS {col_name} {col_type}
            """)
            conn.commit()
            results.append(f"✓ {col_name}")
        except Exception as e:
            results.append(f"✗ {col_name}: {str(e)}")
            conn.rollback()
    
    cur.close()
    conn.close()
    
    return {
        'statusCode': 200,
        'body': json.dumps({'results': results})
    }
