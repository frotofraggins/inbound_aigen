"""
DB Cleanup Lambda - One-time cleanup operations.
"""
import json
import boto3
import psycopg2

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
    Cleanup unfinished dispatcher runs from debugging period.
    """
    
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config, connect_timeout=10)
        
        # Cleanup old unfinished runs
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dispatcher_runs
                SET finished_at = started_at + INTERVAL '1 minute',
                    run_summary_json = '{"note": "Cleaned - historical debugging run"}'::jsonb
                WHERE finished_at IS NULL
                  AND started_at < NOW() - INTERVAL '5 minutes'
                RETURNING run_id
            """)
            
            cleaned_ids = [row[0] for row in cur.fetchall()]
            cleaned_count = len(cleaned_ids)
            conn.commit()
        
        # Verify
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dispatcher_runs WHERE finished_at IS NULL")
            remaining = cur.fetchone()[0]
        
        conn.close()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'cleaned': cleaned_count,
                'remaining_unfinished': remaining
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }
