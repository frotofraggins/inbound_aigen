#!/usr/bin/env python3
"""
Debug Lambda response format to understand what we're getting back
"""

import boto3
import json

def query_db(sql):
    """Query database via Lambda"""
    client = boto3.client('lambda', region_name='us-west-2')
    
    try:
        response = client.invoke(
            FunctionName='ops-pipeline-db-query',
            Payload=json.dumps({'sql': sql})
        )
        
        result = json.loads(response['Payload'].read())
        print(f"Raw Lambda response type: {type(result)}")
        print(f"Raw Lambda response keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
        print(f"Raw Lambda response: {json.dumps(result, indent=2, default=str)}")
        
        if result.get('statusCode') == 200:
            body = json.loads(result['body'])
            print(f"\nBody type: {type(body)}")
            if isinstance(body, list) and len(body) > 0:
                print(f"First item type: {type(body[0])}")
                print(f"First item: {body[0]}")
            return body
        else:
            print(f"Error status code: {result.get('statusCode')}")
            return None
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return None

# Test with table query
print("=" * 80)
print("TESTING TABLE QUERY")
print("=" * 80)

tables_query = """
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name
"""

result = query_db(tables_query)
print(f"\nFinal result type: {type(result)}")
print(f"Final result: {result}")

# Test with count query
print("\n" + "=" * 80)
print("TESTING COUNT QUERY")
print("=" * 80)

count_query = "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public'"
result2 = query_db(count_query)
print(f"\nFinal result type: {type(result2)}")
print(f"Final result: {result2}")
