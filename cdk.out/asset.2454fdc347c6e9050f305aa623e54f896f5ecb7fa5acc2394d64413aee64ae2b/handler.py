import json
import boto3 
import logging
import os
import uuid
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info(f'Received event: {json.dumps(event)}')
    
    # CORS headers - CRITICAL for web requests
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    }
    
    try:
        # Handle preflight OPTIONS request
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'message': 'CORS preflight'})
            }
        
        if event.get('httpMethod') == 'POST':
            return create_liveness_session(event, headers)
        elif event.get('httpMethod') == 'GET':
            return get_liveness_results(event, headers)
        else:
            return {
                'statusCode': 405,
                'headers': headers,
                'body': json.dumps({'error': 'Method not allowed'})
            }
            
    except Exception as e:
        logger.error(f'Unhandled error: {str(e)}')
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }

def create_liveness_session(event, headers):
    """Create Face Liveness Session"""
    try:
        # Initialize Rekognition client
        rekognition = boto3.client('rekognition')
        
        # Parse request body if present
        body = {}
        if event.get('body'):
            try:
                body = json.loads(event['body'])
            except json.JSONDecodeError:
                logger.warning('Invalid JSON in request body')
        
        logger.info(f'Creating liveness session with body: {body}')
        
        # Create liveness session parameters
        user_photos_bucket = os.environ.get('USER_PHOTOS_BUCKET', '')
        params = {
            'Settings': {
                'AuditImagesLimit': 4,
                'OutputConfig': {
                    'S3Bucket': user_photos_bucket,
                    'S3KeyPrefix': 'liveness-sessions/'
                }
            }
        }
        
        # Add client request token for idempotency
        params['ClientRequestToken'] = str(uuid.uuid4())
        
        logger.info(f'Rekognition params: {params}')
        
        # Create the session
        result = rekognition.create_face_liveness_session(**params)
        
        # FIXED: Extract session_id first to avoid f-string syntax error
        session_id = result['SessionId']
        logger.info(f'Liveness session created successfully: {session_id}')
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'sessionId': session_id,
                'status': 'created',
                'timestamp': datetime.utcnow().isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f'Error creating liveness session: {str(e)}')
        
        # Return detailed error for debugging
        error_response = {
            'error': f'Failed to create liveness session: {str(e)}',
            'error_type': type(e).__name__
        }
        
        # Add specific error details
        if hasattr(e, 'response'):
            aws_error = e.response.get('Error', {})
            error_response['aws_error'] = aws_error
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps(error_response)
        }

def get_liveness_results(event, headers):
    """Get Face Liveness Session Results"""
    try:
        # Initialize Rekognition client
        rekognition = boto3.client('rekognition')
        
        # Get session ID from path parameters
        path_parameters = event.get('pathParameters', {})
        session_id = path_parameters.get('sessionId')

        if not session_id:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'sessionId required in path'})
            }
        
        logger.info(f'Getting liveness results for session: {session_id}')
        
        # Get session results
        results = rekognition.get_face_liveness_session_results(
            SessionId=session_id
        )
        
        # Extract reference image information
        reference_image = results.get('ReferenceImage', {})
        has_bytes = bool(reference_image.get('Bytes'))
        has_s3_object = bool(reference_image.get('S3Object'))
        is_available = has_bytes or has_s3_object
        
        confidence = float(results.get('Confidence', 0))
        status = results.get('Status', 'UNKNOWN')
        
        logger.info(f'Liveness results retrieved - Status: {status}, Confidence: {confidence}')
        
        response_body = {
            'sessionId': session_id,
            'status': status,
            'confidence': confidence,
            'referenceImageAvailable': is_available,
            'hasS3Reference': has_s3_object,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Add S3 details if available
        if has_s3_object:
            s3_details = reference_image.get('S3Object')
            response_body['s3Details'] = s3_details
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(response_body)
        }
        
    except Exception as e:
        logger.error(f'Error getting liveness results: {str(e)}')
        
        error_response = {
            'error': f'Failed to get liveness results: {str(e)}',
            'error_type': type(e).__name__
        }
        
        if hasattr(e, 'response'):
            aws_error = e.response.get('Error', {})
            error_response['aws_error'] = aws_error
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps(error_response)
        }  