import json
import boto3
import logging
import os
import sys
sys.path.append('/opt')

# 🆕 Import shared libraries para DetectFaces inmediato
from shared.image_processor import MinimalImageProcessor
from shared.rekognition_client import RekognitionClient

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DOCUMENT_INDEXER_FUNCTION = os.environ['DOCUMENT_INDEXER_FUNCTION']
DOCUMENTS_BUCKET = os.environ['DOCUMENTS_BUCKET']
COLLECTION_ID = os.environ.get('COLLECTION_ID', 'document-faces-collection')

lambda_client = boto3.client('lambda')
s3_client = boto3.client('s3')

# 🆕 Processors para validación inmediata
image_processor = MinimalImageProcessor()
rekognition_client = RekognitionClient(COLLECTION_ID)

def lambda_handler(event, context):
    """
    🆕 API endpoint mejorado para indexar documentos con DetectFaces inmediato
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
            logger.info(f"✅ Document found in S3: {s3_key}")
        except s3_client.exceptions.NoSuchKey:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({
                    'error': f'File {s3_key} not found in bucket {DOCUMENTS_BUCKET}'
                })
            }
        
        # 🆕 STEP 1: IMMEDIATE FACE DETECTION
        logger.info(f"🔍 Performing immediate face detection on {s3_key}")
        
        face_validation_result = validate_document_faces(s3_key)
        
        if not face_validation_result['success']:
            # 🆕 FACE DETECTION FAILED - Delete document and return error
            logger.error(f"❌ Face validation failed for {s3_key}: {face_validation_result['error']}")
            
            try:
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
                logger.info(f"🗑️  Deleted invalid document: {s3_key}")
            except Exception as delete_error:
                logger.error(f"Failed to delete invalid document {s3_key}: {delete_error}")
            
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': f'Document validation failed: {face_validation_result["error"]}',
                    'document_removed': True
                })
            }
        
        # 🆕 STEP 2: Face detection successful - Return success immediately
        # NOTE: Document will be indexed later by user_validator if comparison is successful
        
        logger.info(f"✅ Document validation successful for {s3_key}")
        logger.info(f"📋 Detected faces: {face_validation_result['face_count']}")
        
        # Extract person name for UI display
        person_name = extract_person_name(s3_key)
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'message': 'Document validated successfully - face detected',
                'person_name': person_name,
                'face_count': face_validation_result['face_count'],
                'confidence': face_validation_result.get('confidence', 0),
                'status': 'FACE_DETECTED'
            })
        }
                
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        
        # Try to clean up the uploaded file on any error
        try:
            if 's3_key' in locals():
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
                logger.info(f"Cleaned up failed document: {s3_key}")
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup {s3_key}: {cleanup_error}")
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': f'Internal server error: {str(e)}',
                'document_removed': True
            })
        }

def validate_document_faces(s3_key: str) -> dict:
    """
    🆕 Validar que el documento tiene al menos una cara detectada
    """
    try:
        # STEP 1: Descargar imagen de S3
        response = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
        image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded {s3_key}: {len(image_bytes)} bytes")
        
        # STEP 2: Procesar imagen
        processed_bytes, error = image_processor.process_image(image_bytes, s3_key)
        if error:
            return {
                'success': False,
                'error': f'Image processing failed: {error}'
            }
        
        # STEP 3: Detectar caras
        face_detection = rekognition_client.detect_faces(processed_bytes)
        if not face_detection['success']:
            return {
                'success': False,
                'error': f'Face detection failed: {face_detection["error"]}'
            }
        
        if face_detection['face_count'] == 0:
            return {
                'success': False,
                'error': 'No faces detected in document'
            }
        
        if face_detection['face_count'] > 1:
            logger.warning(f"Multiple faces detected in {s3_key}, but proceeding...")
        
        # STEP 4: Calcular confidence promedio de las caras detectadas
        avg_confidence = 0
        if face_detection.get('faces'):
            confidences = [face.get('Confidence', 0) for face in face_detection['faces']]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        return {
            'success': True,
            'face_count': face_detection['face_count'],
            'confidence': avg_confidence,
            'faces': face_detection.get('faces', [])
        }
        
    except Exception as e:
        logger.error(f"Error validating faces in {s3_key}: {str(e)}")
        return {
            'success': False,
            'error': f'Face validation error: {str(e)}'
        }

def extract_person_name(s3_key: str) -> str:
    """
    Extraer nombre de persona desde el nombre del archivo
    """
    try:
        base_name = os.path.splitext(os.path.basename(s3_key))[0]
        name = base_name.replace('_', ' ').replace('-', ' ')
        remove_words = ['dni', 'cedula', 'passport', 'documento', 'doc', 'id']
        words = [word for word in name.split() if word.lower() not in remove_words]
        return ' '.join(word.capitalize() for word in words) if words else base_name
    except Exception as e:
        logger.error(f"Error extracting person name from {s3_key}: {str(e)}")
        return "Unknown"