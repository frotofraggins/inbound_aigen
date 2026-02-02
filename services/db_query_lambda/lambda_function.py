"""
DB Query Lambda - Read-only queries for operational validation.
VPC-attached for private RDS access.
"""
import json
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_config():
    """Load DB config from AWS."""
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return {
        'host': db_host,
        'port': int(db_port),
        'database': db_name,
        'user': secret_data['username'],
        'password': secret_data['password']
    }

def lambda_handler(event, context):
    """
    Execute read-only SQL query.
    
    Event payload:
    {
        "sql": "SELECT ...",
        "mode": "validation" (optional)
    }
    """
    
    # Safety: Only allow SELECT
    sql = event.get('sql', '')
    if not sql.strip().upper().startswith('SELECT'):
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Only SELECT queries allowed'})
        }
    
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config, connect_timeout=10)
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        
        conn.close()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'rows': rows,
                'count': len(rows)
            }, default=str)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            })
        }
