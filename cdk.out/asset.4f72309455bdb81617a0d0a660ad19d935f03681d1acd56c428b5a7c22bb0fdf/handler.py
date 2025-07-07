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

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    🆕 API para limpiar documentos en caso de timeout o fallo
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
        
        tipo_documento = body.get('tipoDocumento')
        numero_documento = body.get('numeroDocumento')
        reason = body.get('reason', 'TIMEOUT')
        
        if not tipo_documento or not numero_documento:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'tipoDocumento and numeroDocumento are required',
                    'example': {
                        'tipoDocumento': 'DNI',
                        'numeroDocumento': '12345678',
                        'reason': 'TIMEOUT'
                    }
                })
            }
        
        # Construir nombre del archivo del documento
        document_filename = f"{tipo_documento}-{numero_documento}.jpg"
        
        # Verificar si el archivo existe antes de intentar borrarlo
        try:
            s3_client.head_object(Bucket=DOCUMENTS_BUCKET, Key=document_filename)
            
            # El archivo existe, proceder a borrarlo
            logger.info(f"🗑️  Cleaning up document: {document_filename} (reason: {reason})")
            
            s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=document_filename)
            
            logger.info(f"✅ Successfully deleted: {document_filename}")
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'success': True,
                    'message': 'Document cleaned up successfully',
                    'document_key': document_filename,
                    'reason': reason
                })
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == '404' or error_code == 'NoSuchKey':
                # El documento no existe (ya fue borrado o nunca existió)
                logger.info(f"📋 Document not found for cleanup: {document_filename}")
                
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({
                        'success': True,
                        'message': 'Document not found (already cleaned or never existed)',
                        'document_key': document_filename,
                        'reason': reason
                    })
                }
            else:
                # Otro error de S3
                logger.error(f"S3 error during cleanup {document_filename}: {str(e)}")
                return {
                    'statusCode': 500,
                    'headers': headers,
                    'body': json.dumps({
                        'error': f'Error during cleanup: {str(e)}'
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