import json
import boto3
import logging
import os
from botocore.exceptions import ClientError

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DOCUMENTS_BUCKET = os.environ['DOCUMENTS_BUCKET']
USER_PHOTOS_BUCKET = os.environ['USER_PHOTOS_BUCKET']

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Generar presigned URLs para upload directo a S3
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    # CORS headers
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
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
        
        # Parse request body
        body = json.loads(event['body']) if event.get('body') else {}
        
        file_name = body.get('fileName')
        bucket_type = body.get('bucketType')  # 'documents' or 'user-photos'
        content_type = body.get('contentType', 'image/jpeg')
        
        if not file_name or not bucket_type:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'fileName and bucketType are required',
                    'example': {
                        'fileName': 'DNI-12345678.jpg',
                        'bucketType': 'documents',
                        'contentType': 'image/jpeg'
                    }
                })
            }
        
        # Determine bucket
        if bucket_type == 'documents':
            bucket_name = DOCUMENTS_BUCKET
        elif bucket_type == 'user-photos':
            bucket_name = USER_PHOTOS_BUCKET
        else:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'Invalid bucketType. Must be "documents" or "user-photos"'
                })
            }
        
        # Generate presigned URL
        try:
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': file_name,
                    'ContentType': content_type
                },
                ExpiresIn=300  # 5 minutes
            )
            
            logger.info(f"Generated presigned URL for {file_name} in {bucket_name}")
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'success': True,
                    'uploadUrl': presigned_url,
                    'bucket': bucket_name,
                    'key': file_name,
                    'expiresIn': 300
                })
            }
            
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({
                    'error': f'Failed to generate upload URL: {str(e)}'
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