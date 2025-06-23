import json
import boto3
import logging
import os
import uuid
from datetime import datetime
import sys
from decimal import Decimal
sys.path.append('/opt')

# Imports locales (se empaquetan con la Lambda)
from shared.image_processor import MinimalImageProcessor
from shared.rekognition_client import RekognitionClient



# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
COLLECTION_ID = os.environ['COLLECTION_ID']
INDEXED_DOCUMENTS_TABLE = os.environ['INDEXED_DOCUMENTS_TABLE']
DOCUMENTS_BUCKET = os.environ['DOCUMENTS_BUCKET']

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(INDEXED_DOCUMENTS_TABLE)

# Processors
image_processor = MinimalImageProcessor()
rekognition_client = RekognitionClient(COLLECTION_ID)

def lambda_handler(event, context):
    """
    Handler principal para indexar documentos de identidad
    
    Acepta:
    1. Invocación manual con lista de documentos
    2. S3 event (futuro) 
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Asegurar que la colección existe
        if not rekognition_client.create_collection_if_not_exists():
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to create Rekognition collection'})
            }
        
        # Procesar según tipo de evento
        if 'action' in event and event['action'] == 'index_all':
            # Indexar todos los documentos en el bucket
            return index_all_documents()
        elif 'documents' in event:
            # Indexar documentos específicos
            return index_specific_documents(event['documents'])
        elif 'Records' in event:
            # S3 Event (futuro)
            return process_s3_event(event)
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid event format'})
            }
            
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }
def index_all_documents():
    """
    Indexar todos los documentos en el bucket
    """
    logger.info("Starting to index all documents")
    
    try:
        # Listar objetos en el bucket
        response = s3_client.list_objects_v2(Bucket=DOCUMENTS_BUCKET)
        
        if 'Contents' not in response:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No documents found in bucket',
                    'indexed_count': 0
                })
            }
        
        results = []
        success_count = 0
        error_count = 0
        
        for obj in response['Contents']:
            s3_key = obj['Key']
            
            # Solo procesar imágenes
            if not s3_key.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
                
            logger.info(f"Processing document: {s3_key}")
            
            try:
                result = index_single_document(s3_key)
                results.append(result)
                
                if result['success']:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing {s3_key}: {str(e)}")
                results.append({
                    'document': s3_key,
                    'success': False,
                    'error': str(e)
                })
                error_count += 1
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Indexing completed. Success: {success_count}, Errors: {error_count}',
                'indexed_count': success_count,
                'error_count': error_count,
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to list documents: {str(e)}'})
        }
def index_single_document(s3_key: str) -> dict:
    """
    Indexar un documento específico
    """
    try:
        # STEP 1: Descargar imagen de S3
        response = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
        image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded {s3_key}: {len(image_bytes)} bytes")
        
        # STEP 2: Preprocessing mínimo
        processed_bytes, error = image_processor.process_image(image_bytes, s3_key)
        if error:
            return {
                'document': s3_key,
                'success': False, 
                'error': f'Preprocessing failed: {error}'
            }
        
        # STEP 3: Validar que hay exactamente una cara
        face_detection = rekognition_client.detect_faces(processed_bytes)
        if not face_detection['success']:
            return {
                'document': s3_key,
                'success': False,
                'error': f'Face detection failed: {face_detection["error"]}'
            }
        
        if face_detection['face_count'] == 0:
            return {
                'document': s3_key,
                'success': False,
                'error': 'No faces detected in document'
            }
        
        if face_detection['face_count'] > 1:
            logger.warning(f"Multiple faces detected in {s3_key}, using first face")
        
        # STEP 4: Generar ID único para el documento
        document_id = generate_document_id(s3_key)
        
        # STEP 5: Indexar cara en Rekognition
        index_result = rekognition_client.index_face(processed_bytes, document_id)
        if not index_result['success']:
            return {
                'document': s3_key,
                'success': False,
                'error': f'Indexing failed: {index_result["error"]}'
            }
        
        # STEP 6: Extraer nombre de persona del filename (simplificado para PoC)
        person_name = extract_person_name(s3_key)
        
        # STEP 7: Almacenar metadatos en DynamoDB
        metadata = {
            'document_id': document_id,
            'face_id': index_result['face_id'],
            's3_key': s3_key,
            'person_name': person_name,
            'document_type': detect_document_type(s3_key),
            'index_timestamp': datetime.utcnow().isoformat(),
            'confidence_score': Decimal(str(index_result['confidence'])),
            'face_bounding_box': json.dumps(index_result['bounding_box']),
            'processing_status': 'INDEXED_SUCCESSFULLY'
        }
        
        table.put_item(Item=metadata)
        
        logger.info(f"Successfully indexed {s3_key} as {document_id}")
        
        return {
            'document': s3_key,
            'success': True,
            'document_id': document_id,
            'face_id': index_result['face_id'],
            'person_name': person_name,
            'confidence': index_result['confidence']
        }
        
    except Exception as e:
        logger.error(f"Error indexing {s3_key}: {str(e)}")
        return {
            'document': s3_key,
            'success': False,
            'error': str(e)
        }
def generate_document_id(s3_key: str) -> str:
    """
    Generar ID único para documento basado en filename
    """
    # Extraer nombre base sin extensión
    base_name = os.path.splitext(os.path.basename(s3_key))[0]
    
    # Limpiar caracteres especiales
    clean_name = ''.join(c for c in base_name if c.isalnum() or c in ['_', '-']).lower()
    
    # Agregar timestamp para unicidad
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    return f"{clean_name}_{timestamp}"

def extract_person_name(s3_key: str) -> str:
    """
    Extraer nombre de persona del filename (lógica simplificada para PoC)
    """
    # Extraer nombre base
    base_name = os.path.splitext(os.path.basename(s3_key))[0]
    
    # Reemplazar guiones bajos y guiones con espacios
    name = base_name.replace('_', ' ').replace('-', ' ')
    
    # Remover palabras comunes de documento
    remove_words = ['dni', 'cedula', 'passport', 'documento', 'doc', 'id']
    words = [word for word in name.split() if word.lower() not in remove_words]
    
    # Capitalizar cada palabra
    return ' '.join(word.capitalize() for word in words) if words else base_name

def detect_document_type(s3_key: str) -> str:
    """
    Detectar tipo de documento basado en filename
    """
    filename_lower = s3_key.lower()
    
    if 'dni' in filename_lower:
        return 'DNI'
    elif 'cedula' in filename_lower:
        return 'CEDULA'
    elif 'passport' in filename_lower:
        return 'PASSPORT'
    elif 'license' in filename_lower:
        return 'LICENSE'
    else:
        return 'DOCUMENT'

def index_specific_documents(document_list: list):
    """
    Indexar lista específica de documentos
    """
    results = []
    success_count = 0
    
    for s3_key in document_list:
        try:
            result = index_single_document(s3_key)
            results.append(result)
            if result['success']:
                success_count += 1
        except Exception as e:
            results.append({
                'document': s3_key,
                'success': False,
                'error': str(e)
            })
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Processed {len(document_list)} documents, {success_count} successful',
            'indexed_count': success_count,
            'results': results
        })
    }

def process_s3_event(event):
    """
    Procesar evento S3 (para futuras implementaciones)
    """
    # Por ahora, solo log del evento
    logger.info("S3 event processing not implemented yet")
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'S3 event logged'})
    }
