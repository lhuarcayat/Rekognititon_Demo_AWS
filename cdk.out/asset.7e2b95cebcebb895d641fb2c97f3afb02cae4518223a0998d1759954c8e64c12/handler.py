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
    Handler principal mejorado para indexar documentos de identidad
    
    Modos disponibles:
    1. {"action": "smart_index_all"} - Indexa todos, saltando duplicados
    2. {"action": "index_new_only"} - Solo documentos nuevos
    3. {"action": "index_all"} - Modo clásico (mantener compatibilidad)
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Asegurar que la colección existe
        if not rekognition_client.create_collection_if_not_exists():
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to create Rekognition collection'})
            }
        
        # Determinar modo de operación
        action = event.get('action', 'smart_index_all')  # Default inteligente
        
        if action == 'smart_index_all' or action == 'index_all':
            # MODO 1: Indexar todos los documentos, saltando duplicados
            return smart_index_all_documents()
            
        elif action == 'index_new_only':
            # MODO 2: Solo documentos nuevos
            return index_new_documents_only()
            
        elif 'documents' in event:
            # Indexar documentos específicos (mantener funcionalidad)
            return index_specific_documents(event['documents'])
            
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid event format',
                    'supported_actions': ['smart_index_all', 'index_new_only'],
                    'example': '{"action": "smart_index_all"}'
                })
            }
            
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }

def smart_index_all_documents():
    """
    MODO 1: Indexar todos los documentos, pero saltando duplicados
    """
    logger.info("🔄 SMART INDEX ALL: Processing all documents, skipping duplicates")
    
    try:
        # 1. Obtener documentos ya indexados
        existing_docs = get_already_indexed_documents()
        existing_s3_keys = {doc['s3_key'] for doc in existing_docs}
        
        logger.info(f"Found {len(existing_docs)} already indexed documents")
        
        # 2. Listar todos los archivos en el bucket
        response = s3_client.list_objects_v2(Bucket=DOCUMENTS_BUCKET)
        
        if 'Contents' not in response:
            return create_response(
                message='No documents found in bucket',
                new_indexed=0, skipped=0, errors=0
            )
        
        # 3. Procesar cada archivo
        results = []
        new_indexed_count = 0
        skipped_count = 0
        error_count = 0
        
        for obj in response['Contents']:
            s3_key = obj['Key']
            
            # Solo procesar imágenes
            if not s3_key.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            
            # ✅ VERIFICAR SI YA FUE INDEXADO
            if s3_key in existing_s3_keys:
                logger.info(f"⏭️  SKIPPING already indexed: {s3_key}")
                results.append({
                    'document': s3_key,
                    'status': 'SKIPPED_DUPLICATE',
                    'message': 'Already indexed'
                })
                skipped_count += 1
                continue
            
            # 🆕 PROCESAR DOCUMENTO NUEVO
            logger.info(f"🆕 INDEXING NEW document: {s3_key}")
            
            try:
                result = index_single_document(s3_key)
                results.append(result)
                
                if result['success']:
                    new_indexed_count += 1
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
        
        return create_response(
            message=f'Smart indexing completed',
            new_indexed=new_indexed_count,
            skipped=skipped_count, 
            errors=error_count,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Error in smart indexing: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Smart indexing failed: {str(e)}'})
        }

def index_new_documents_only():
    """
    MODO 2: Indexar SOLO documentos nuevos (no duplicar NADA)
    """
    logger.info("🆕 INDEX NEW ONLY: Processing only new documents")
    
    try:
        # 1. Obtener documentos ya indexados
        existing_docs = get_already_indexed_documents()
        existing_s3_keys = {doc['s3_key'] for doc in existing_docs}
        
        # 2. Obtener TODOS los archivos en S3
        response = s3_client.list_objects_v2(Bucket=DOCUMENTS_BUCKET)
        
        if 'Contents' not in response:
            return create_response(
                message='No documents found in bucket',
                new_indexed=0, total_existing=len(existing_s3_keys)
            )
        
        # 3. Identificar documentos completamente nuevos
        new_documents = []
        for obj in response['Contents']:
            s3_key = obj['Key']
            
            if (s3_key.lower().endswith(('.jpg', '.jpeg', '.png')) and 
                s3_key not in existing_s3_keys):
                new_documents.append(s3_key)
        
        if not new_documents:
            return create_response(
                message='No new documents to index',
                new_indexed=0,
                total_existing=len(existing_s3_keys),
                total_in_bucket=len([obj for obj in response['Contents'] 
                                   if obj['Key'].lower().endswith(('.jpg', '.jpeg', '.png'))])
            )
        
        # 4. Indexar solo documentos nuevos
        logger.info(f"Found {len(new_documents)} new documents to index")
        
        results = []
        success_count = 0
        error_count = 0
        
        for s3_key in new_documents:
            try:
                logger.info(f"🆕 Indexing NEW document: {s3_key}")
                result = index_single_document(s3_key)
                results.append(result)
                
                if result['success']:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Error indexing new document {s3_key}: {str(e)}")
                results.append({
                    'document': s3_key,
                    'success': False,
                    'error': str(e)
                })
                error_count += 1
        
        return create_response(
            message=f'New documents indexing completed',
            new_indexed=success_count,
            errors=error_count,
            total_new_found=len(new_documents),
            results=results
        )
        
    except Exception as e:
        logger.error(f"Error indexing new documents: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to index new documents: {str(e)}'})
        }

def get_already_indexed_documents():
    """
    Obtener lista de documentos ya indexados desde DynamoDB
    """
    try:
        response = table.scan()
        return response['Items']
    except Exception as e:
        logger.error(f"Error getting indexed documents: {str(e)}")
        return []

def index_single_document(s3_key: str) -> dict:
    """
    Indexar un documento específico con verificación de duplicados
    """
    try:
        # VERIFICACIÓN FINAL DE DUPLICADOS (por seguridad)
        existing = check_document_already_indexed(s3_key)
        if existing:
            return {
                'document': s3_key,
                'success': True,
                'status': 'ALREADY_INDEXED',
                'document_id': existing['document_id'],
                'message': 'Document already indexed, skipped'
            }
        
        # STEP 1: Descargar imagen de S3
        response = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
        image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded {s3_key}: {len(image_bytes)} bytes")
        
        # STEP 2: Preprocessing
        processed_bytes, error = image_processor.process_image(image_bytes, s3_key)
        if error:
            return {'document': s3_key, 'success': False, 'error': f'Preprocessing failed: {error}'}
        
        # STEP 3: Detectar caras
        face_detection = rekognition_client.detect_faces(processed_bytes)
        if not face_detection['success']:
            return {'document': s3_key, 'success': False, 'error': f'Face detection failed: {face_detection["error"]}'}
        
        if face_detection['face_count'] == 0:
            return {'document': s3_key, 'success': False, 'error': 'No faces detected in document'}
        
        if face_detection['face_count'] > 1:
            logger.warning(f"Multiple faces detected in {s3_key}, using first face")
        
        # STEP 4: Generar ID único
        document_id = generate_document_id(s3_key)
        
        # STEP 5: ⚡ TRANSACCIÓN ATÓMICA
        try:
            # 5a. Indexar en Rekognition
            index_result = rekognition_client.index_face(processed_bytes, document_id)
            if not index_result['success']:
                return {'document': s3_key, 'success': False, 'error': f'Rekognition indexing failed: {index_result["error"]}'}
            
            # 5b. Guardar metadata INMEDIATAMENTE
            person_name = extract_person_name(s3_key)
            
            metadata = {
                'document_id': document_id,
                'face_id': index_result['face_id'],
                'image_id': index_result['image_id'],
                'collection_id':index_result['collection_id'],
                's3_key': s3_key,
                'person_name': person_name,
                'document_type': detect_document_type(s3_key),
                'index_timestamp': datetime.utcnow().isoformat(),
                'confidence_score': Decimal(str(index_result['confidence'])),
                'face_bounding_box': json.dumps(index_result['bounding_box']),
                'processing_status': 'INDEXED_SUCCESSFULLY'
            }
            
            table.put_item(Item=metadata)
            
            logger.info(f"✅ Successfully indexed {s3_key} → {document_id}")
            
            return {
                'document': s3_key,
                'success': True,
                'status': 'NEWLY_INDEXED',
                'document_id': document_id,
                'face_id': index_result['face_id'],
                'person_name': person_name,
                'confidence': index_result['confidence']
            }
            
        except Exception as metadata_error:
            # 🛡️ ROLLBACK: Eliminar cara de Rekognition si falló metadata
            logger.error(f"Metadata save failed for {s3_key}, rolling back...")
            
            try:
                if 'index_result' in locals() and index_result.get('success'):
                    rekognition_client.rekognition.delete_faces(
                        CollectionId=COLLECTION_ID,
                        FaceIds=[index_result['face_id']]
                    )
                    logger.info(f"Rolled back face {index_result['face_id']} from Rekognition")
            except Exception as rollback_error:
                logger.error(f"CRITICAL: Rollback failed: {rollback_error}")
            
            return {'document': s3_key, 'success': False, 'error': f'Atomic transaction failed: {str(metadata_error)}'}
        
    except Exception as e:
        logger.error(f"Error indexing {s3_key}: {str(e)}")
        return {'document': s3_key, 'success': False, 'error': str(e)}

def check_document_already_indexed(s3_key: str) -> dict:
    """
    Verificar si un documento ya fue indexado
    """
    try:
        response = table.scan(
            FilterExpression='s3_key = :key',
            ExpressionAttributeValues={':key': s3_key}
        )
        
        if response['Items']:
            return response['Items'][0]
        return None
        
    except Exception as e:
        logger.error(f"Error checking document {s3_key}: {str(e)}")
        return None

def create_response(message, **kwargs):
    """
    Crear respuesta estandarizada
    """
    body = {'message': message, **kwargs}
    
    # Log resumen
    if 'new_indexed' in kwargs:
        logger.info(f"📊 SUMMARY: {kwargs['new_indexed']} new indexed, {kwargs.get('skipped', 0)} skipped, {kwargs.get('errors', 0)} errors")
    
    return {
        'statusCode': 200,
        'body': json.dumps(body)
    }

# Funciones auxiliares (sin cambios)
def generate_document_id(s3_key: str) -> str:
    base_name = os.path.splitext(os.path.basename(s3_key))[0]
    clean_name = ''.join(c for c in base_name if c.isalnum() or c in ['_', '-']).lower()
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return f"{clean_name}_{timestamp}"

def extract_person_name(s3_key: str) -> str:
    base_name = os.path.splitext(os.path.basename(s3_key))[0]
    name = base_name.replace('_', ' ').replace('-', ' ')
    remove_words = ['dni', 'cedula', 'passport', 'documento', 'doc', 'id']
    words = [word for word in name.split() if word.lower() not in remove_words]
    return ' '.join(word.capitalize() for word in words) if words else base_name

def detect_document_type(s3_key: str) -> str:
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
    Indexar documentos específicos (mantener funcionalidad existente)
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
            results.append({'document': s3_key, 'success': False, 'error': str(e)})
    
    return create_response(
        message=f'Processed {len(document_list)} specific documents',
        new_indexed=success_count,
        results=results
    )
