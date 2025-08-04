import json
import boto3 
import logging
import os
import uuid
from datetime import datetime
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info(f'Received event: {json.dumps(event)}')
    
    # CORS headers - CRITICAL for web requests
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Amz-Target, X-Amz-User-Agent'
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
    """Create Face Liveness Session with enhanced configuration"""
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
        
        # Enhanced session configuration for better compatibility
        user_photos_bucket = os.environ.get('USER_PHOTOS_BUCKET', '')
        
        # Enhanced parameters for Amplify v6 compatibility
        params = {
            'Settings': {
                'AuditImagesLimit': 4,  # Maximum audit images
                'OutputConfig': {
                    'S3Bucket': user_photos_bucket,
                    'S3KeyPrefix': 'liveness-sessions/'
                }
            }
        }
        
        # Add client request token for idempotency
        client_token = str(uuid.uuid4())
        params['ClientRequestToken'] = client_token
        
        logger.info(f'Rekognition params: {params}')
        logger.info(f'Using S3 bucket for audit images: {user_photos_bucket}')
        
        # Create the session
        result = rekognition.create_face_liveness_session(**params)
        
        session_id = result['SessionId']
        logger.info(f'✅ Liveness session created successfully: {session_id}')
        logger.info(f'Client token: {client_token}')
        
        # Enhanced response with additional metadata
        response_body = {
            'sessionId': session_id,
            'status': 'created',
            'timestamp': datetime.utcnow().isoformat(),
            'region': 'us-east-1',
            'clientToken': client_token,
            'auditImagesConfig': {
                'bucket': user_photos_bucket,
                'prefix': 'liveness-sessions/',
                'maxImages': 4
            },
            'configuration': {
                'amplifyVersion': 'v6',
                'livenessVersion': '3.x',
                'supportedFeatures': ['face-movement', 'color-display', 'audit-images']
            }
        }
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(response_body)
        }
        
    except ClientError as e:
        aws_error = e.response.get('Error', {})
        error_code = aws_error.get('Code', 'Unknown')
        error_message = aws_error.get('Message', str(e))
        
        logger.error(f'AWS error creating liveness session: {error_code} - {error_message}')
        
        # Enhanced error handling for common issues
        if error_code == 'AccessDeniedException':
            error_response = {
                'error': 'Insufficient permissions to create Face Liveness session',
                'error_type': 'PERMISSION_ERROR',
                'details': 'Check IAM roles and policies for Rekognition permissions',
                'aws_error_code': error_code
            }
        elif error_code == 'InvalidParameterException':
            error_response = {
                'error': 'Invalid parameters for Face Liveness session',
                'error_type': 'PARAMETER_ERROR',
                'details': 'Check S3 bucket configuration and parameters',
                'aws_error_code': error_code
            }
        elif error_code == 'ServiceQuotaExceededException':
            error_response = {
                'error': 'Service quota exceeded for Face Liveness',
                'error_type': 'QUOTA_ERROR',
                'details': 'Too many concurrent sessions or requests',
                'aws_error_code': error_code
            }
        else:
            error_response = {
                'error': f'AWS service error: {error_message}',
                'error_type': 'AWS_SERVICE_ERROR',
                'aws_error_code': error_code,
                'aws_error_message': error_message
            }
        
        return {
            'statusCode': 400 if error_code in ['InvalidParameterException', 'AccessDeniedException'] else 500,
            'headers': headers,
            'body': json.dumps(error_response)
        }
        
    except Exception as e:
        logger.error(f'Unexpected error creating liveness session: {str(e)}')
        
        error_response = {
            'error': f'Unexpected error creating liveness session: {str(e)}',
            'error_type': 'INTERNAL_ERROR'
        }
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps(error_response)
        }

def get_liveness_results(event, headers):
    """Get Face Liveness Session Results with enhanced metadata"""
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
                'body': json.dumps({
                    'error': 'sessionId required in path',
                    'example': '/liveness-session/{sessionId}'
                })
            }
        
        logger.info(f'Getting liveness results for session: {session_id}')
        
        try:
            # Get session results
            results = rekognition.get_face_liveness_session_results(
                SessionId=session_id
            )
            
            # Extract comprehensive information
            session_status = results.get('Status', 'UNKNOWN')
            confidence = float(results.get('Confidence', 0))
            
            # Reference image information
            reference_image = results.get('ReferenceImage', {})
            has_bytes = bool(reference_image.get('Bytes'))
            has_s3_object = bool(reference_image.get('S3Object'))
            is_available = has_bytes or has_s3_object
            
            # Audit images information
            audit_images = results.get('AuditImages', [])
            
            logger.info(f'Liveness results retrieved - Status: {session_status}, Confidence: {confidence}')
            logger.info(f'Reference image available: {is_available}, Audit images: {len(audit_images)}')
            
            # Enhanced response body
            response_body = {
                'sessionId': session_id,
                'status': session_status,
                'confidence': confidence,
                'isLive': confidence > 90 and session_status == 'SUCCEEDED',
                'timestamp': datetime.utcnow().isoformat(),
                
                # Reference image details
                'referenceImage': {
                    'available': is_available,
                    'hasBytes': has_bytes,
                    'hasS3Object': has_s3_object,
                    's3Details': reference_image.get('S3Object') if has_s3_object else None,
                    'boundingBox': reference_image.get('BoundingBox') if reference_image else None
                },
                
                # Audit images information
                'auditImages': {
                    'count': len(audit_images),
                    'available': len(audit_images) > 0,
                    'images': audit_images if audit_images else []
                },
                
                # Session metadata
                'metadata': {
                    'sessionAge': 'calculated_in_frontend',
                    'region': 'us-east-1',
                    'service': 'aws-rekognition-liveness'
                }
            }
            
            # Add quality information if available
            if 'Quality' in results:
                response_body['quality'] = results['Quality']
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(response_body)
            }
            
        except ClientError as e:
            aws_error = e.response.get('Error', {})
            error_code = aws_error.get('Code', 'Unknown')
            error_message = aws_error.get('Message', str(e))
            
            logger.error(f'AWS error getting liveness results: {error_code} - {error_message}')
            
            if error_code == 'SessionNotFoundException':
                error_response = {
                    'error': 'Liveness session not found',
                    'error_type': 'SESSION_NOT_FOUND',
                    'sessionId': session_id,
                    'details': 'Session may have expired or never existed',
                    'aws_error_code': error_code
                }
                status_code = 404
            elif error_code == 'AccessDeniedException':
                error_response = {
                    'error': 'Insufficient permissions to access liveness results',
                    'error_type': 'PERMISSION_ERROR',
                    'sessionId': session_id,
                    'aws_error_code': error_code
                }
                status_code = 403
            else:
                error_response = {
                    'error': f'AWS service error: {error_message}',
                    'error_type': 'AWS_SERVICE_ERROR',
                    'sessionId': session_id,
                    'aws_error_code': error_code
                }
                status_code = 500
            
            return {
                'statusCode': status_code,
                'headers': headers,
                'body': json.dumps(error_response)
            }
        
    except Exception as e:
        logger.error(f'Unexpected error getting liveness results: {str(e)}')
        
        error_response = {
            'error': f'Unexpected error getting liveness results: {str(e)}',
            'error_type': 'INTERNAL_ERROR',
            'sessionId': session_id if 'session_id' in locals() else 'unknown'
        }
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps(error_response)
        }