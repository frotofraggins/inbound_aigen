import json
import os
import boto3
import psycopg2
from datetime import datetime

def lambda_handler(event, context):
    """
    Smoke test Lambda to verify RDS connectivity from VPC.
    Reads DB config from SSM and Secrets Manager, connects to Postgres,
    and runs SELECT version() to confirm connectivity.
    """
    
    print(json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "event": "smoke_test_start",
        "message": "Starting database connectivity test"
    }))
    
    try:
        # Initialize AWS clients
        ssm = boto3.client('ssm', region_name='us-west-2')
        secrets = boto3.client('secretsmanager', region_name='us-west-2')
        
        # Read DB connection details from SSM
        print(json.dumps({"event": "ssm_read_start", "message": "Reading SSM parameters"}))
        
        db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
        db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
        db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
        
        print(json.dumps({
            "event": "ssm_read_success",
            "db_host": db_host,
            "db_port": db_port,
            "db_name": db_name
        }))
        
        # Read DB credentials from Secrets Manager
        print(json.dumps({"event": "secrets_read_start", "message": "Reading Secrets Manager"}))
        
        secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
        secret_data = json.loads(secret_value['SecretString'])
        
        db_user = secret_data['username']
        db_password = secret_data['password']
        
        print(json.dumps({
            "event": "secrets_read_success",
            "username": db_user
        }))
        
        # Attempt connection to PostgreSQL
        print(json.dumps({
            "event": "db_connect_start",
            "message": f"Connecting to {db_host}:{db_port}/{db_name}"
        }))
        
        conn = psycopg2.connect(
            host=db_host,
            port=int(db_port),
            database=db_name,
            user=db_user,
            password=db_password,
            connect_timeout=5
        )
        
        print(json.dumps({
            "event": "db_connect_success",
            "message": "Successfully connected to database"
        }))
        
        # Execute test query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        # Success!
        result = {
            "success": True,
            "db_host": db_host,
            "db_name": db_name,
            "db_port": db_port,
            "postgres_version": version,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        print(json.dumps({
            "event": "smoke_test_complete",
            **result
        }))
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except psycopg2.OperationalError as e:
        error_msg = str(e)
        error_type = "connection_error"
        
        if "timeout" in error_msg.lower():
            error_type = "timeout"
        elif "could not translate host name" in error_msg.lower():
            error_type = "dns_error"
        elif "password authentication failed" in error_msg.lower():
            error_type = "auth_error"
        elif "no route to host" in error_msg.lower() or "network unreachable" in error_msg.lower():
            error_type = "network_error"
            
        print(json.dumps({
            "event": "smoke_test_failed",
            "success": False,
            "error_type": error_type,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }))
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error_type': error_type,
                'error': error_msg
            })
        }
        
    except Exception as e:
        error_msg = str(e)
        print(json.dumps({
            "event": "smoke_test_failed",
            "success": False,
            "error_type": "unexpected_error",
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat()
        }))
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error_type': 'unexpected_error',
                'error': error_msg
            })
        }
