import json
import boto3
import logging
import os

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DOCUMENT_INDEXER_FUNCTION = os.environ['DOCUMENT_INDEXER_FUNCTION']
DOCUMENTS_BUCKET = os.environ['DOCUMENTS_BUCKET']

lambda_client = boto3.client('lambda')
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    API endpoint para invocar document indexer
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
        
        s3_key = body.get('s3_key')
        
        if not s3_key:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 's3_key is required',
                    'example': {'s3_key': 'DNI-12345678.jpg'}
                })
            }
        
        # Verificar que el archivo existe en S3
        try:
            s3_client.head_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
        except s3_client.exceptions.NoSuchKey:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({
                    'error': f'File {s3_key} not found in bucket {DOCUMENTS_BUCKET}'
                })
            }
        
        # Preparar payload para document indexer
        indexer_payload = {
            'action': 'index_new_only',
            'documents': [s3_key]
        }
        
        # Invocar document indexer lambda
        try:
            response = lambda_client.invoke(
                FunctionName=DOCUMENT_INDEXER_FUNCTION,
                InvocationType='RequestResponse',  # Synchronous
                Payload=json.dumps(indexer_payload)
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            logger.info(f"Document indexer response: {response_payload}")
            
            # Parse the response body if it's JSON string
            if 'body' in response_payload:
                indexer_result = json.loads(response_payload['body'])
            else:
                indexer_result = response_payload
            
            # Check if indexing was successful
            if response_payload.get('statusCode') == 200:
                results = indexer_result.get('results', [])
                
                if results and len(results) > 0:
                    result = results[0]
                    
                    if result.get('success'):
                        # SUCCESS - Document indexed successfully
                        return {
                            'statusCode': 200,
                            'headers': headers,
                            'body': json.dumps({
                                'success': True,
                                'message': 'Document indexed successfully',
                                'document_id': result.get('document_id'),
                                'person_name': result.get('person_name'),
                                'confidence': result.get('confidence'),
                                'status': result.get('status', 'NEWLY_INDEXED')
                            })
                        }
                    else:
                        # FAILED - Remove file from S3 and return error
                        error_message = result.get('error', 'Unknown indexing error')
                        
                        try:
                            s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
                            logger.info(f"Deleted failed document: {s3_key}")
                        except Exception as delete_error:
                            logger.error(f"Failed to delete {s3_key}: {delete_error}")
                        
                        return {
                            'statusCode': 400,
                            'headers': headers,
                            'body': json.dumps({
                                'success': False,
                                'error': f'Document validation failed: {error_message}',
                                'document_removed': True
                            })
                        }
                else:
                    return {
                        'statusCode': 400,
                        'headers': headers,
                        'body': json.dumps({
                            'success': False,
                            'error': 'No processing results returned'
                        })
                    }
            else:
                # Lambda returned error status
                return {
                    'statusCode': response_payload.get('statusCode', 500),
                    'headers': headers,
                    'body': json.dumps({
                        'success': False,
                        'error': indexer_result.get('error', 'Document indexer failed')
                    })
                }
                
        except Exception as lambda_error:
            logger.error(f"Error invoking document indexer: {str(lambda_error)}")
            
            # Try to clean up the uploaded file
            try:
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
                logger.info(f"Cleaned up failed document: {s3_key}")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup {s3_key}: {cleanup_error}")
            
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': f'Failed to process document: {str(lambda_error)}',
                    'document_removed': True
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