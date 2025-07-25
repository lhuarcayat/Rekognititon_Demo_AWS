import json
import boto3
import logging
import os
import uuid
from datetime import datetime
import time
import sys
from decimal import Decimal
<<<<<<< HEAD
import re
=======
import base64
>>>>>>> 4fa7a03532f01c2cd7cfa79f246061c428000bde
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
    🆕 Handler actualizado para validación con errores específicos y manejo de reintentos
    Triggered por S3 events cuando se sube foto al bucket user-photos
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    start_time = time.time()
    
    try:
        if 'Records' in event:

        # Procesar eventos S3
<<<<<<< HEAD
        for record in event['Records']:
            if record['eventSource'] == 'aws:s3':
                bucket_name = record['s3']['bucket']['name']
                user_photo_key = record['s3']['object']['key']
                
                logger.info(f"🆕 Processing user photo with retry support: {user_photo_key}")
                
                result = validate_user_photo_with_specific_errors(user_photo_key, start_time)
                
                # Log resultado final
                processing_time = (time.time() - start_time) * 1000
                logger.info(f"Validation completed for {user_photo_key}: {result['status']} in {processing_time:.0f}ms")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Processing completed successfully'})
        }
        
=======
            for record in event['Records']:
                if record['eventSource'] == 'aws:s3':
                    bucket_name = record['s3']['bucket']['name']
                    s3_key = record['s3']['object']['key']
                    
                    logger.info(f"Processing user photo: {s3_key}")
                    
                    result = validate_user_photo(s3_key, start_time)
                    
                    # Log resultado final
                    processing_time = (time.time() - start_time) * 1000
                    logger.info(f"Validation completed for {s3_key}: {result['status']} in {processing_time:.0f}ms")
            
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Processing completed successfully'})
            }
        elif 'httpMethod' in event:
            return handle_web_api_request(event,context)
        else:
            return{
                'statusCode':400,
                'body':json.dumps({'error':'Unsupported event type'})
            }
>>>>>>> 4fa7a03532f01c2cd7cfa79f246061c428000bde
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }

def validate_user_photo_with_specific_errors(user_photo_key: str, start_time: float) -> dict:
    """
    🆕 VALIDACIÓN CON ERRORES ESPECÍFICOS Y MANEJO DE REINTENTOS
    Separar DetectFaces vs CompareFaces para feedback específico
    """
    comparison_id = generate_comparison_id()
    
    try:
        # STEP 1: Extraer información del archivo
        document_info = extract_document_info_from_user_photo(user_photo_key)
        if not document_info:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='INVALID_FILENAME',
                error='Invalid user photo filename format',
                error_type='FILENAME_ERROR',
                allow_retry=False
            )
        
        tipo_documento = document_info['tipo_documento']
        numero_documento = document_info['numero_documento']
        attempt_number = document_info.get('attempt_number', 1)
        
        logger.info(f"📋 Processing attempt #{attempt_number} for document: {tipo_documento}-{numero_documento}")
        
        # STEP 2: Verificar documento existe
        document_key = f"{tipo_documento}-{numero_documento}.jpg"
        
        try:
            s3_client.head_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
            logger.info(f"✅ Found corresponding document: {document_key}")
        except s3_client.exceptions.NoSuchKey:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='DOCUMENT_NOT_FOUND',
                error=f'Corresponding document not found: {document_key}',
                error_type='DOCUMENT_MISSING',
                allow_retry=False
            )
        
        # STEP 3: Descargar imagen de usuario
        bucket_name = os.environ['USER_PHOTOS_BUCKET']
        user_response = s3_client.get_object(Bucket=bucket_name, Key=user_photo_key)
        user_image_bytes = user_response['Body'].read()
        
        logger.info(f"Downloaded user photo {user_photo_key}: {len(user_image_bytes)} bytes")
        
        # STEP 4: Procesar imagen de usuario
        processed_user_bytes, user_error = image_processor.process_image(user_image_bytes, user_photo_key)
        if user_error:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='USER_PROCESSING_ERROR',
                error=f'User image preprocessing failed: {user_error}',
                error_type='IMAGE_PROCESSING_ERROR',
                allow_retry=True  # 🆕 Permitir reintento en errores de procesamiento
            )
        
        # 🆕 STEP 5A: DETECTAR CARAS EN USUARIO (SEPARADO)
        logger.info(f"🔍 STEP 1: Detecting faces in user photo...")
        
        user_face_detection = rekognition_client.detect_faces(processed_user_bytes)
        if not user_face_detection['success']:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='DETECTFACES_FAILED',
                error=f'Face detection failed in user photo: {user_face_detection["error"]}',
                error_type='NO_FACE_DETECTED',  # 🆕 Error específico para frontend
                allow_retry=True,  # 🆕 Permitir reintento
                attempt_number=attempt_number
            )
        
        if user_face_detection['face_count'] == 0:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='DETECTFACES_FAILED',
                error='No faces detected in user photo',
                error_type='NO_FACE_DETECTED',  # 🆕 Error específico
                allow_retry=True,  # 🆕 Permitir reintento
                attempt_number=attempt_number
            )
        
        logger.info(f"✅ Face detection successful: {user_face_detection['face_count']} faces found")
        
        # STEP 6: Descargar y procesar imagen de documento
        doc_response = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
        document_image_bytes = doc_response['Body'].read()
        
        logger.info(f"Downloaded document {document_key}: {len(document_image_bytes)} bytes")
        
        processed_doc_bytes, doc_error = image_processor.process_image(document_image_bytes, document_key)
        if doc_error:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='DOCUMENT_PROCESSING_ERROR',
                error=f'Document image preprocessing failed: {doc_error}',
                error_type='IMAGE_PROCESSING_ERROR',
                allow_retry=True
            )
        
        # 🆕 STEP 7: COMPARE FACES (SEPARADO)
        logger.info(f"🔍 STEP 2: Performing CompareFaces between user and document...")
        
        comparison = rekognition_client.compare_faces(
            processed_user_bytes,  # Source: foto del usuario
            processed_doc_bytes,   # Target: foto del documento
            threshold=75.0         # Threshold más bajo para capturar más casos
        )
        
        if not comparison['success']:
            return store_validation_result(
                comparison_id, user_photo_key, start_time,
                status='COMPAREFACES_FAILED',
                error=f'CompareFaces failed: {comparison["error"]}',
                error_type='COMPARISON_ERROR',
                allow_retry=True,  # 🆕 Permitir reintento en errores técnicos
                attempt_number=attempt_number
            )
        
        # 🆕 STEP 8: EVALUACIÓN DE RESULTADOS CON CATEGORÍAS ESPECÍFICAS
        if comparison['match_found']:
            confidence = comparison['similarity']
            logger.info(f"✅ CompareFaces result: {confidence:.1f}% similarity")
            
            # 🆕 CATEGORIZACIÓN MÁS GRANULAR DE RESULTADOS
            if confidence >= 90:
                status = 'MATCH_CONFIRMED'
                error_type = None
                allow_retry = False
                should_index_document = True
            elif confidence >= 80:
                status = 'MATCH_CONFIRMED'
                error_type = None
                allow_retry = False
                should_index_document = True
            elif confidence >= 70:
                status = 'POSSIBLE_MATCH'
                error_type = None
                allow_retry = False
                should_index_document = True
            else:
                # 🆕 Confidence muy baja - permitir reintento
                return store_validation_result(
                    comparison_id, user_photo_key, start_time,
                    status='COMPAREFACES_FAILED',
                    error=f'Low confidence match: {confidence:.1f}%',
                    error_type='LOW_CONFIDENCE',  # 🆕 Error específico
                    allow_retry=True,
                    attempt_number=attempt_number,
                    confidence_score=Decimal(str(confidence))
                )
            
            # STEP 9: Indexar documento si es exitoso
            person_name = None
            document_indexed = False
            
            if should_index_document:
                existing_document = check_document_already_indexed(document_key)
                
                if existing_document:
                    logger.info(f"📋 Document already indexed: {document_key}")
                    person_name = existing_document.get('person_name', 'Unknown')
                    document_indexed = False
                else:
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
                comparison_method='DIRECT_COMPARE',
                error_type=error_type,
                allow_retry=allow_retry,
                attempt_number=attempt_number
            )
        
        else:
            # 🆕 NO MATCH ENCONTRADO - Permitir reintentos
            logger.info(f"❌ No match found between user and document (attempt #{attempt_number})")
            
            # 🆕 DECIDIR ACCIÓN BASADA EN NÚMERO DE INTENTOS
            if attempt_number >= 5:  # Máximo 5 intentos
                # Demasiados intentos fallidos - cleanup y no más reintentos
                existing_document = check_document_already_indexed(document_key)
                
                if not existing_document:
                    logger.info(f"🗑️  Max attempts reached - deleting document for new user: {document_key}")
                    try:
                        s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
                        logger.info(f"✅ Document deleted: {document_key}")
                    except Exception as delete_error:
                        logger.error(f"❌ Failed to delete document {document_key}: {delete_error}")
                
                return store_validation_result(
                    comparison_id, user_photo_key, start_time,
                    status='COMPAREFACES_FAILED',
                    error='No facial match found after maximum attempts',
                    error_type='NO_MATCH_FOUND',
                    allow_retry=False,  # 🆕 No más reintentos
                    confidence_score=Decimal('0'),
                    document_image_key=document_key,
                    comparison_method='DIRECT_COMPARE',
                    attempt_number=attempt_number
                )
            else:
                # Permitir más intentos
                return store_validation_result(
                    comparison_id, user_photo_key, start_time,
                    status='COMPAREFACES_FAILED',
                    error='No facial match found',
                    error_type='NO_MATCH_FOUND',  # 🆕 Error específico
                    allow_retry=True,  # 🆕 Permitir más intentos
                    confidence_score=Decimal('0'),
                    document_image_key=document_key,
                    comparison_method='DIRECT_COMPARE',
                    attempt_number=attempt_number
                )
        
    except Exception as e:
        logger.error(f"Error validating {user_photo_key}: {str(e)}")
        return store_validation_result(
            comparison_id, user_photo_key, start_time,
            status='ERROR',
            error=str(e),
            error_type='SYSTEM_ERROR',
            allow_retry=True  # 🆕 Permitir reintento en errores del sistema
        )

def extract_document_info_from_user_photo(user_photo_key: str) -> dict:
    """
    🆕 Extraer información incluyendo número de intento
    Formato: {tipoDocumento}-{numeroDocumento}-user-{timestamp}-attempt-{number}.jpg
    """
    try:
        filename = os.path.basename(user_photo_key)
        base_name = os.path.splitext(filename)[0]
        
        # 🆕 Pattern actualizado para incluir attempt number
        pattern = r'^([A-Z]+)-([^-]+)-user-([^-]+)-attempt-(\d+)$'
        match = re.match(pattern, base_name)
        
        if match:
            tipo_documento = match.group(1)
            numero_documento = match.group(2)
            timestamp = match.group(3)
            attempt_number = int(match.group(4))
            
            return {
                'tipo_documento': tipo_documento,
                'numero_documento': numero_documento,
                'timestamp': timestamp,
                'attempt_number': attempt_number
            }
        
        # Fallback: si no tiene attempt number, asumir que es el primer intento
        pattern_old = r'^([A-Z]+)-([^-]+)-user-(.+)$'
        match_old = re.match(pattern_old, base_name)
        
        if match_old:
            return {
                'tipo_documento': match_old.group(1),
                'numero_documento': match_old.group(2),
                'timestamp': match_old.group(3),
                'attempt_number': 1
            }
        
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
    Invocar document indexer para indexar documento exitoso
    """
    try:
        indexer_payload = {
            'action': 'index_new_only',
            'documents': [document_key]
        }
        
        response = lambda_client.invoke(
            FunctionName=DOCUMENT_INDEXER_FUNCTION,
            InvocationType='RequestResponse',
            Payload=json.dumps(indexer_payload)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        logger.info(f"Document indexer response: {response_payload}")
        
        if 'body' in response_payload:
            indexer_result = json.loads(response_payload['body'])
        else:
            indexer_result = response_payload
        
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
    🆕 Almacenar resultado con campos adicionales para reintentos
    """
    processing_time = (time.time() - start_time) * 1000
    timestamp = datetime.utcnow().isoformat()
    
    # TTL: 1 año desde ahora
    ttl = int(time.time()) + (365 * 24 * 60 * 60)
    
    # Procesar kwargs para DynamoDB
    processed_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, float):
            processed_kwargs[key] = Decimal(str(value)) 
        else:
            processed_kwargs[key] = value
    
    # 🆕 Campos adicionales para el frontend
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
        
        # 🆕 Return con campos específicos para el frontend
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
            'error': str(e),
            'error_type': 'SYSTEM_ERROR',
            'allow_retry': True
        }

def generate_comparison_id() -> str:
    """
    Generar ID único para comparación
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"comp_{timestamp}_{unique_id}"

def handle_web_api_request(event,context):
    try:
        path =event['path']
        body=json.loads(event.get('body','{}'))
        if path.endswith('/users/lookup'):
            return lookup_user_from_web(body)
        elif path.endswith('users/validate'):
            return validate_liveness_from_web(body)
        else:
            return{
                'statusCode': 404,
                'headers':{'Access-Control-Allow-Origin':'*'},
                'body':json.dumps({'error':'Endpoint not found'})
            }
    except Exception as e:
        return{
            'statusCode':500,
            'headers':{'Access-Control-Allow-Origin':'*'},
            'body':json.dumps({'error':str(e)})
        }
def lookup_user_from_web(request_data):
    try:
        user_data=request_data.get('user_data',{})
        document_type=user_data.get('document_type')
        document_number=user_data.get('document_number')
        response = documents_table.scan(
            FilterExpression='document_type=:dt AND contains(s3_key,:dn)',
            ExpressionAttributeValues={':dt':document_type,':dn':document_number}
        )
        user_exists = len(response['Items'])>0
        return{
            'statusCode':200,
            'headers':{'Access-Control-Allow-Origin':'*'},
            'body':json.dumps({
                'user_exists': user_exists,
                'user_data':response['Items'][0] if user_exists else None,
                'message': 'Usuario encontrado' if user_exists else 'Usuario nuevo'
            })
        }
    except Exception as e:
        return {
            'statusCode':500,
            'headers':{'Access-Control-Allow-Origin':'*'},
            'body':json.dumps({'error':str(e)})
        }

def validate_liveness_from_web(request_data):
    try:
        liveness_image=request_data.get('liveness_image','')
        if liveness_image.startswith('data:image'):
            image_data=liveness_image.split(',')[1]
        else:
            image_data = liveness_image
        image_bytes = base64.b64decode(image_data)

        processed_bytes, error = image_processor.process_image(image_bytes, 'liveness.jpg')
        if error:
            return{
                'statusCode':400,
                'headers':{'Access-Control-Allow-Origin':'*'},
                'body':json.dumps({'success':False,'error':error})
            }
        search_result=rekognition_client.search_faces_by_image(processed_bytes,threshold=75,max_faces=5)
        if not search_result['success'] or not search_result['face_matches']:
            return {
                'statusCode':200,
                'headers':{'Access-Control-Allow-Origin':'*'},
                'body':json.dumps({
                    'success':True,
                    'status': 'NO_MATCH_FOUND',
                    'confidence':0
                })
            }
        best_match= search_result['face_matches'][0]
        similarity=best_match['Similarity']
        face_id=best_match['Face']['FaceId']
        document_metadata = get_document_by_face_id(face_id)
        status ='MATCH_CONFIRMED' if similarity >= 85 else 'POSSIBLE_MATCH'
        return {
            'statusCode':200,
            'headers':{'Access-Control-Allow-Origin':'*'},
            'body':json.dumps({
                'success':True,
                'status':status,
                'confidence':similarity,
                'person_name':document_metadata.get('person_name') if document_metadata else 'Usuario'
            })
        }
    except Exception as e:
            return {
                'statusCode':500,
                'headers':{'Access-Control-Allow-Origin':'*'},
                'body':json.dumps({'success':False,'error':str(e)})
            }




