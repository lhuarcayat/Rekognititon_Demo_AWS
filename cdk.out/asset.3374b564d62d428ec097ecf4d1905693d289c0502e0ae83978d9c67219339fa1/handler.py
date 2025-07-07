import json
import boto3
import logging
import os
import uuid
from datetime import datetime
import time
import sys
from decimal import Decimal
import re
sys.path.append('/opt')

# Imports locales
from shared.image_processor import MinimalImageProcessor
from shared.rekognition_client import RekognitionClient

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
COLLECTION_ID = os.environ['COLLECTION_ID']
COMPARISON_RESULTS_TABLE = os.environ['COMPARISON_RESULTS_TABLE']
INDEXED_DOCUMENTS_TABLE = os.environ['INDEXED_DOCUMENTS_TABLE']
DOCUMENTS_BUCKET = os.environ['DOCUMENTS_BUCKET']
DOCUMENT_INDEXER_FUNCTION = os.environ.get('DOCUMENT_INDEXER_FUNCTION', 'rekognition-poc-document-indexer')

# Clients
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')
results_table = dynamodb.Table(COMPARISON_RESULTS_TABLE)
documents_table = dynamodb.Table(INDEXED_DOCUMENTS_TABLE)

# Processors
image_processor = MinimalImageProcessor()
rekognition_client = RekognitionClient(COLLECTION_ID)

def lambda_handler(event, context):
    """
    🆕 Handler actualizado para validar fotos de usuarios con CompareFaces directo
    Triggered por S3 events cuando se sube foto al bucket user-photos
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    start_time = time.time()
    
    try:
        # Procesar eventos S3
        for record in event['Records']:
            if record['eventSource'] == 'aws:s3':
                bucket_name = record['s3']['bucket']['name']
                user_photo_key = record['s3']['object']['key']
                
                logger.info(f"🆕 Processing user photo with new flow: {user_photo_key}")
                
                result = validate_user_photo_direct_compare(user_photo_key, start_time)
                
                # Log resultado final
                processing_time = (time.time() - start_time) * 1000
                logger.info(f"Validation completed for {user_photo_key}: {result['status']} in {processing_time:.0f}ms")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Processing completed successfully'})
        }
        
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }

def validate_user_photo_direct_compare(user_photo_key: str, start_time: float) -> dict:
    """
    🆕 NUEVA LÓGICA: CompareFaces directo entre rostro y documento
    """
    comparison_id = generate_comparison_id()
    
    try:
        # STEP 1: Extraer información del nombre del archivo del rostro
        # Formato esperado: {tipoDocumento}-{numeroDocumento}-user-{timestamp}.jpg
        document_info = extract_document_info_from_user_photo(user_photo_key)
        if not document_info:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='INVALID_FILENAME',
                error='Invalid user photo filename format'
            )
        
        tipo_documento = document_info['tipo_documento']
        numero_documento = document_info['numero_documento']
        
        logger.info(f"📋 Extracted document info: {tipo_documento}-{numero_documento}")
        
        # STEP 2: Verificar si el documento correspondiente existe en S3
        document_key = f"{tipo_documento}-{numero_documento}.jpg"
        
        try:
            s3_client.head_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
            logger.info(f"✅ Found corresponding document: {document_key}")
        except s3_client.exceptions.NoSuchKey:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='DOCUMENT_NOT_FOUND',
                error=f'Corresponding document not found: {document_key}'
            )
        
        # STEP 3: Descargar imagen de usuario
        bucket_name = os.environ['USER_PHOTOS_BUCKET']
        user_response = s3_client.get_object(Bucket=bucket_name, Key=user_photo_key)
        user_image_bytes = user_response['Body'].read()
        
        logger.info(f"Downloaded user photo {user_photo_key}: {len(user_image_bytes)} bytes")
        
        # STEP 4: Descargar imagen de documento
        doc_response = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
        document_image_bytes = doc_response['Body'].read()
        
        logger.info(f"Downloaded document {document_key}: {len(document_image_bytes)} bytes")
        
        # STEP 5: Procesar ambas imágenes
        processed_user_bytes, user_error = image_processor.process_image(user_image_bytes, user_photo_key)
        if user_error:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='USER_PROCESSING_ERROR',
                error=f'User image preprocessing failed: {user_error}'
            )
        
        processed_doc_bytes, doc_error = image_processor.process_image(document_image_bytes, document_key)
        if doc_error:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='DOCUMENT_PROCESSING_ERROR',
                error=f'Document image preprocessing failed: {doc_error}'
            )
        
        # STEP 6: Detectar caras en la imagen del usuario
        user_face_detection = rekognition_client.detect_faces(processed_user_bytes)
        if not user_face_detection['success']:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='NO_FACE_DETECTED',
                error=f'Face detection failed in user photo: {user_face_detection["error"]}'
            )
        
        if user_face_detection['face_count'] == 0:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='NO_FACE_DETECTED',
                error='No faces detected in user photo'
            )
        
        # STEP 7: 🆕 CompareFaces DIRECTO (sin SearchFacesByImage)
        logger.info(f"🔍 Performing DIRECT CompareFaces between user and document...")
        
        comparison = rekognition_client.compare_faces(
            processed_user_bytes,  # Source: foto del usuario
            processed_doc_bytes,   # Target: foto del documento
            threshold=80.0         # Threshold para comparación
        )
        
        if not comparison['success']:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='COMPARISON_ERROR',
                error=f'CompareFaces failed: {comparison["error"]}'
            )
        
        # STEP 8: Evaluar resultado y determinar siguiente acción
        if comparison['match_found']:
            confidence = comparison['similarity']
            logger.info(f"✅ CompareFaces result: {confidence:.1f}% similarity")
            
            # Determinar status basado en confidence
            if confidence >= 85:
                status = 'MATCH_CONFIRMED'
                should_index_document = True
            elif confidence >= 75:
                status = 'POSSIBLE_MATCH'
                should_index_document = True
            else:
                status = 'LOW_CONFIDENCE_MATCH'
                should_index_document = False
            
            # STEP 9: 🆕 INDEXAR DOCUMENTO SOLO SI ES EXITOSO Y ES USUARIO NUEVO
            person_name = None
            document_indexed = False
            
            if should_index_document:
                # Verificar si el documento ya está indexado
                existing_document = check_document_already_indexed(document_key)
                
                if existing_document:
                    logger.info(f"📋 Document already indexed: {document_key}")
                    person_name = existing_document.get('person_name', 'Unknown')
                    document_indexed = False  # Ya estaba indexado
                else:
                    # 🆕 INDEXAR DOCUMENTO POR PRIMERA VEZ
                    logger.info(f"🆕 Indexing document for first time: {document_key}")
                    
                    index_result = await_index_document(document_key)
                    if index_result and index_result.get('success'):
                        person_name = index_result.get('person_name', 'Unknown')
                        document_indexed = True
                        logger.info(f"✅ Document indexed successfully: {document_key}")
                    else:
                        logger.warning(f"⚠️  Document indexing failed: {document_key}")
                        document_indexed = False
            
            # STEP 10: Almacenar resultado exitoso
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status=status,
                confidence_score=Decimal(str(confidence)),
                person_name=person_name,
                document_image_key=document_key,
                document_indexed=document_indexed,
                comparison_method='DIRECT_COMPARE'
            )
        
        else:
            # 🆕 NO MATCH - Borrar documento si es usuario nuevo
            logger.info(f"❌ No match found between user and document")
            
            # Verificar si documento ya está indexado
            existing_document = check_document_already_indexed(document_key)
            
            if not existing_document:
                # Es usuario nuevo y falló - borrar documento
                logger.info(f"🗑️  Deleting failed document for new user: {document_key}")
                try:
                    s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
                    logger.info(f"✅ Document deleted: {document_key}")
                except Exception as delete_error:
                    logger.error(f"❌ Failed to delete document {document_key}: {delete_error}")
            else:
                # Es usuario existente - no borrar documento
                logger.info(f"📋 Existing user - keeping document: {document_key}")
            
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='NO_MATCH_FOUND',
                confidence_score=Decimal('0'),
                document_image_key=document_key,
                comparison_method='DIRECT_COMPARE'
            )
        
    except Exception as e:
        logger.error(f"Error validating {user_photo_key}: {str(e)}")
        return store_validation_result(
            comparison_id, user_photo_key, start_time,
            status='ERROR',
            error=str(e)
        )

def extract_document_info_from_user_photo(user_photo_key: str) -> dict:
    """
    🆕 Extraer información del documento desde el nombre del archivo del rostro
    Formato esperado: {tipoDocumento}-{numeroDocumento}-user-{timestamp}.jpg
    """
    try:
        # Remover extensión y path
        filename = os.path.basename(user_photo_key)
        base_name = os.path.splitext(filename)[0]
        
        # Pattern: TIPO-NUMERO-user-TIMESTAMP
        pattern = r'^([A-Z]+)-([^-]+)-user-(.+)$'
        match = re.match(pattern, base_name)
        
        if match:
            tipo_documento = match.group(1)
            numero_documento = match.group(2)
            timestamp = match.group(3)
            
            return {
                'tipo_documento': tipo_documento,
                'numero_documento': numero_documento,
                'timestamp': timestamp
            }
        else:
            logger.error(f"Filename doesn't match expected pattern: {base_name}")
            return None
            
    except Exception as e:
        logger.error(f"Error extracting document info from {user_photo_key}: {str(e)}")
        return None

def check_document_already_indexed(document_key: str) -> dict:
    """
    Verificar si un documento ya está indexado en DynamoDB
    """
    try:
        response = documents_table.scan(
            FilterExpression='s3_key = :key',
            ExpressionAttributeValues={':key': document_key}
        )
        
        if response['Items']:
            return response['Items'][0]
        return None
        
    except Exception as e:
        logger.error(f"Error checking if document indexed {document_key}: {str(e)}")
        return None

def await_index_document(document_key: str) -> dict:
    """
    🆕 Invocar document indexer para indexar documento exitoso
    """
    try:
        # Preparar payload para document indexer
        indexer_payload = {
            'action': 'index_new_only',
            'documents': [document_key]
        }
        
        # Invocar document indexer lambda
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
                    return {
                        'success': True,
                        'document_id': result.get('document_id'),
                        'person_name': result.get('person_name'),
                        'confidence': result.get('confidence')
                    }
                else:
                    logger.error(f"Document indexing failed: {result.get('error')}")
                    return {'success': False, 'error': result.get('error')}
            else:
                logger.error("No processing results returned from indexer")
                return {'success': False, 'error': 'No processing results'}
        else:
            logger.error(f"Document indexer returned error: {indexer_result.get('error')}")
            return {'success': False, 'error': indexer_result.get('error')}
            
    except Exception as e:
        logger.error(f"Error invoking document indexer: {str(e)}")
        return {'success': False, 'error': str(e)}

def store_validation_result(comparison_id: str, user_image_key: str, start_time: float, **kwargs) -> dict:
    """
    Almacenar resultado de validación en DynamoDB
    """
    processing_time = (time.time() - start_time) * 1000
    timestamp = datetime.utcnow().isoformat()
    
    # TTL: 1 año desde ahora
    ttl = int(time.time()) + (365 * 24 * 60 * 60)
    processed_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, float):
            processed_kwargs[key] = Decimal(str(value)) 
        else:
            processed_kwargs[key] = value  
    item = {
        'comparison_id': comparison_id,
        'timestamp': timestamp,
        'user_image_key': user_image_key,
        'processing_time_ms': int(processing_time),
        'ttl': ttl,
        **processed_kwargs
    }
    
    try:
        results_table.put_item(Item=item)
        logger.info(f"Stored validation result: {comparison_id}")
        
        return {
            'comparison_id': comparison_id,
            'processing_time_ms': int(processing_time),
            **kwargs
        }
        
    except Exception as e:
        logger.error(f"Error storing result: {str(e)}")
        return {
            'comparison_id': comparison_id,
            'status': 'STORAGE_ERROR',
            'error': str(e)
        }

def generate_comparison_id() -> str:
    """
    Generar ID único para comparación
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"comp_{timestamp}_{unique_id}"