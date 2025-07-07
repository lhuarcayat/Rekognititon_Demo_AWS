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
    🆕 API para verificar si un documento ya existe en S3
    Usado para determinar si es usuario nuevo o existente
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
        
        if not tipo_documento or not numero_documento:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'tipoDocumento and numeroDocumento are required',
                    'example': {
                        'tipoDocumento': 'DNI',
                        'numeroDocumento': '12345678'
                    }
                })
            }
        
        # Construir nombre del archivo del documento
        document_filename = f"{tipo_documento}-{numero_documento}.jpg"
        
        # Verificar si el archivo existe en S3
        try:
            s3_client.head_object(Bucket=DOCUMENTS_BUCKET, Key=document_filename)
            
            # El documento existe
            logger.info(f"Document exists: {document_filename}")
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'exists': True,
                    'document_key': document_filename,
                    'message': 'Documento encontrado en el sistema'
                })
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == '404' or error_code == 'NoSuchKey':
                # El documento no existe
                logger.info(f"Document not found: {document_filename}")
                
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({
                        'exists': False,
                        'document_key': document_filename,
                        'message': 'Documento no encontrado, se requerirá registro completo'
                    })
                }
            else:
                # Otro error de S3
                logger.error(f"S3 error checking document {document_filename}: {str(e)}")
                return {
                    'statusCode': 500,
                    'headers': headers,
                    'body': json.dumps({
                        'error': f'Error accessing document storage: {str(e)}'
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