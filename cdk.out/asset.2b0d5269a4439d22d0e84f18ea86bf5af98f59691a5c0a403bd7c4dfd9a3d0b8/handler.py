import json
import boto3
import logging
import os
from decimal import Decimal

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
COMPARISON_RESULTS_TABLE = os.environ['COMPARISON_RESULTS_TABLE']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(COMPARISON_RESULTS_TABLE)

def lambda_handler(event, context):
    """
    Check validation results for a specific document number
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    # CORS headers
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    try:
        # Handle preflight OPTIONS request
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'message': 'CORS preflight'})
            }
        
        # Get document number from path parameters
        path_parameters = event.get('pathParameters', {})
        numero_documento = path_parameters.get('numero_documento') if path_parameters else None
        
        if not numero_documento:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'numero_documento path parameter is required'
                })
            }
        
        logger.info(f"Checking validation results for document: {numero_documento}")
        
        # Search for validation results
        # We need to scan because we're looking for user_image_key that contains the document number
        try:
            response = table.scan(
                FilterExpression='contains(user_image_key, :doc_number)',
                ExpressionAttributeValues={
                    ':doc_number': numero_documento
                }
            )
            
            items = response['Items']
            
            if not items:
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({
                        'match_found': False,
                        'message': 'No validation results found for this document'
                    })
                }
            
            # Get the most recent result (highest timestamp)
            latest_result = max(items, key=lambda x: x['timestamp'])
            
            logger.info(f"Found validation result: {latest_result['comparison_id']}")
            
            # Convert Decimal to float for JSON serialization
            result_data = convert_decimals(latest_result)
            
            # Determine if match was successful
            status = result_data.get('status', '')
            confidence = float(result_data.get('confidence_score', 0))
            
            match_found = status in ['MATCH_CONFIRMED', 'POSSIBLE_MATCH']
            
            response_body = {
                'match_found': match_found,
                'status': status,
                'confidence': confidence,
                'comparison_id': result_data.get('comparison_id'),
                'timestamp': result_data.get('timestamp'),
                'processing_time_ms': result_data.get('processing_time_ms'),
            }
            
            # Add additional details if match was found
            if match_found:
                response_body.update({
                    'person_name': result_data.get('person_name'),
                    'matched_face_id': result_data.get('matched_face_id'),
                    'search_confidence': float(result_data.get('search_confidence', 0))
                })
            
            # Add error info if present
            if 'error' in result_data:
                response_body['error'] = result_data['error']
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(response_body)
            }
            
        except Exception as db_error:
            logger.error(f"Error querying DynamoDB: {str(db_error)}")
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({
                    'error': f'Failed to query validation results: {str(db_error)}'
                })
            }
    
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': f'Internal server error: {str(e)}'
            })
        }

def convert_decimals(obj):
    """
    Convert DynamoDB Decimal objects to float for JSON serialization
    """
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(v) for v in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj