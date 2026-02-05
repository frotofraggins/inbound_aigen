"""
Ops Pipeline Healthcheck Lambda
Runs every 5 minutes to emit CloudWatch metrics for system health monitoring.
"""
import json
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')
lambda_client = boto3.client('lambda')

QUERY_LAMBDA = 'ops-pipeline-db-query'
NAMESPACE = 'OPsPipeline'

HEALTH_QUERY = """
SELECT 
    -- Core lag metrics (0 if no data)
    COALESCE(EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(ts) FROM lane_telemetry)))::int, 0) AS telemetry_lag_sec,
    COALESCE(EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(computed_at) FROM lane_features_clean)))::int, 0) AS feature_lag_sec,
    COALESCE(EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(computed_at) FROM watchlist_state)))::int, 0) AS watchlist_lag_sec,
    COALESCE(EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(created_at) FROM dispatch_recommendations)))::int, 0) AS reco_lag_sec,
    COALESCE(EXTRACT(EPOCH FROM (NOW() - (SELECT MAX(simulated_ts) FROM dispatch_executions)))::int, 0) AS exec_lag_sec,
    
    -- Presence metrics (1 if data exists, 0 if table empty)
    CASE WHEN EXISTS(SELECT 1 FROM dispatch_recommendations LIMIT 1) THEN 1 ELSE 0 END AS reco_data_present,
    CASE WHEN EXISTS(SELECT 1 FROM dispatch_executions LIMIT 1) THEN 1 ELSE 0 END AS exec_data_present,
    
    -- Throughput metrics
    (SELECT COUNT(*) FROM lane_telemetry WHERE ts >= NOW() - INTERVAL '10 minutes') AS bars_written_10m,
    (SELECT COUNT(DISTINCT ticker) FROM lane_features_clean WHERE computed_at >= NOW() - INTERVAL '10 minutes') AS features_computed_10m,
    
    -- Critical safety metrics
    (SELECT COUNT(*) FROM dispatcher_runs 
     WHERE finished_at IS NULL 
       AND started_at >= NOW() - INTERVAL '10 minutes') AS unfinished_runs,
    (SELECT COUNT(*) FROM (
        SELECT recommendation_id 
        FROM dispatch_executions 
        GROUP BY recommendation_id 
        HAVING COUNT(*) > 1
    ) x) AS duplicate_recos
"""


def lambda_handler(event, context):
    """
    5-minute healthcheck: query DB via ops-pipeline-db-query, emit CloudWatch metrics.
    """
    try:
        # Query DB via existing Lambda
        response = lambda_client.invoke(
            FunctionName=QUERY_LAMBDA,
            InvocationType='RequestResponse',
            Payload=json.dumps({'sql': HEALTH_QUERY})
        )
        
        result = json.loads(response['Payload'].read())
        body = json.loads(result.get('body', '{}'))
        
        if body.get('error'):
            print(f"Query error: {body['error']}")
            return {'statusCode': 500, 'body': json.dumps({'error': body['error']})}
        
        metrics = body['rows'][0]
        timestamp = datetime.utcnow()
        
        # Emit CloudWatch metrics
        metric_data = [
            # Lag metrics (always emit, 0 if no data)
            {
                'MetricName': 'TelemetryLag',
                'Value': metrics['telemetry_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'FeatureLag',
                'Value': metrics['feature_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'WatchlistLag',
                'Value': metrics['watchlist_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'RecommendationLag',
                'Value': metrics['reco_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'ExecutionLag',
                'Value': metrics['exec_lag_sec'],
                'Unit': 'Seconds',
                'Timestamp': timestamp
            },
            
            # Presence metrics (1 if data exists, 0 if empty)
            {
                'MetricName': 'RecoDataPresent',
                'Value': metrics['reco_data_present'],
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'ExecDataPresent',
                'Value': metrics['exec_data_present'],
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            
            # Throughput metrics
            {
                'MetricName': 'BarsWritten10m',
                'Value': metrics['bars_written_10m'],
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'FeaturesComputed10m',
                'Value': metrics['features_computed_10m'],
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            
            # Critical safety metrics
            {
                'MetricName': 'UnfinishedRuns',
                'Value': metrics['unfinished_runs'],
                'Unit': 'Count',
                'Timestamp': timestamp
            },
            {
                'MetricName': 'DuplicateExecutions',
                'Value': metrics['duplicate_recos'],
                'Unit': 'Count',
                'Timestamp': timestamp
            }
        ]
        
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=metric_data
        )
        
        print(f"Emitted metrics: {json.dumps(metrics)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Health metrics emitted',
                'metrics': metrics
            })
        }
        
    except Exception as e:
        print(f"Healthcheck error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
