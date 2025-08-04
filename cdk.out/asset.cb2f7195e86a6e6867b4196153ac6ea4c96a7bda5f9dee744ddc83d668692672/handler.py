import json
import boto3
import logging
import os
import uuid
from datetime import datetime
import time
import sys
from decimal import Decimal
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

# NEW: Validation mode configuration
VALIDATION_MODE = os.environ.get('VALIDATION_MODE', 'HYBRID')
DIRECT_COMPARE_THRESHOLD = float(os.environ.get('DIRECT_COMPARE_THRESHOLD', '80.0'))

# Clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
results_table = dynamodb.Table(COMPARISON_RESULTS_TABLE)
documents_table = dynamodb.Table(INDEXED_DOCUMENTS_TABLE)

# Processors
image_processor = MinimalImageProcessor()
rekognition_client = RekognitionClient(COLLECTION_ID)

def decimal_serializer(obj):
    """
    JSON serializer para objetos Decimal de DynamoDB
    """
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def lambda_handler(event, context):
    """
    Enhanced handler with support for direct document image key comparison
    
    Supported payload formats:
    1. Hybrid mode: {"validation_mode": "HYBRID", "user_image_key": "photo.jpg"}
    2. Direct with document_id: {"validation_mode": "DIRECT_COMPARE", "user_image_key": "photo.jpg", "target_document_id": "doc_123"}
    3. NEW - Direct with image key: {"validation_mode": "DIRECT_COMPARE", "user_image_key": "photo.jpg", "document_image_key": "juan_dni.jpg"}
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    start_time = time.time()
    
    try:
        # Handle manual invocation with specific mode
        if 'validation_mode' in event:
            validation_mode = event['validation_mode']
            user_image_key = event.get('user_image_key')
            
            logger.info(f"Manual invocation - Mode: {validation_mode}, User Image: {user_image_key}")
            
            if validation_mode == 'HYBRID':
                result = validate_hybrid_mode(user_image_key, start_time)
                
            elif validation_mode == 'DIRECT_COMPARE':
                # NEW: Check if using document_image_key or target_document_id
                if 'document_image_key' in event:
                    document_image_key = event['document_image_key']
                    logger.info(f"Using DIRECT_COMPARE with document_image_key: {document_image_key}")
                    result = validate_direct_compare_by_image_key(user_image_key, document_image_key, start_time)
                    
                elif 'target_document_id' in event:
                    target_document_id = event['target_document_id']
                    logger.info(f"Using DIRECT_COMPARE with target_document_id: {target_document_id}")
                    result = validate_direct_compare_by_document_id(user_image_key, target_document_id, start_time)
                    
                else:
                    return {
                        'statusCode': 400,
                        'body': json.dumps({
                            'error': 'DIRECT_COMPARE mode requires either document_image_key or target_document_id',
                            'examples': [
                                '{"validation_mode": "DIRECT_COMPARE", "user_image_key": "photo.jpg", "document_image_key": "juan_dni.jpg"}',
                                '{"validation_mode": "DIRECT_COMPARE", "user_image_key": "photo.jpg", "target_document_id": "juan_perez_123"}'
                            ]
                        })
                    }
            else:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid validation mode',
                        'supported_modes': ['HYBRID', 'DIRECT_COMPARE']
                    })
                }
            
            return {
                'statusCode': 200,
                'body': json.dumps(result, default=decimal_serializer)
            }
        
        # Handle S3 events (automatic validation) - unchanged
        for record in event['Records']:
            if record['eventSource'] == 'aws:s3':
                bucket_name = record['s3']['bucket']['name']
                s3_key = record['s3']['object']['key']
                
                logger.info(f"Processing user photo: {s3_key}")
                
                # Use configured validation mode for S3 events
                if VALIDATION_MODE == 'DIRECT_COMPARE':
                    target_document_id = extract_target_document_from_key(s3_key)
                    if target_document_id:
                        result = validate_direct_compare_by_document_id(s3_key, target_document_id, start_time)
                    else:
                        logger.warning(f"No target document found for {s3_key}, falling back to HYBRID mode")
                        result = validate_hybrid_mode(s3_key, start_time)
                else:
                    result = validate_hybrid_mode(s3_key, start_time)
                
                processing_time = (time.time() - start_time) * 1000
                logger.info(f"Validation completed for {s3_key}: {result['status']} in {processing_time:.0f}ms")
        
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

def validate_direct_compare_by_image_key(user_image_key: str, document_image_key: str, start_time: float) -> dict:
    """
    NEW: Modo directo usando document_image_key (nombre del archivo en S3)
    """
    comparison_id = generate_comparison_id()
    logger.info(f"🎯 DIRECT COMPARE BY IMAGE KEY: {user_image_key} vs {document_image_key}")
    
    try:
        # STEP 1: Descargar imagen de usuario
        bucket_name = os.environ['USER_PHOTOS_BUCKET']
        response = s3_client.get_object(Bucket=bucket_name, Key=user_image_key)
        user_image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded user photo {user_image_key}: {len(user_image_bytes)} bytes")
        
        # STEP 2: Descargar imagen del documento usando document_image_key
        try:
            doc_response = s3_client.get_object(
                Bucket=DOCUMENTS_BUCKET, 
                Key=document_image_key
            )
            document_image_bytes = doc_response['Body'].read()
            logger.info(f"Downloaded document image {document_image_key}: {len(document_image_bytes)} bytes")
        except Exception as e:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='DOCUMENT_IMAGE_NOT_FOUND',
                validation_mode='DIRECT_COMPARE_BY_IMAGE_KEY',
                document_image_key=document_image_key,
                error=f'Failed to download document image: {str(e)}'
            )
        
        # STEP 3: Buscar metadatos del documento (opcional, para enriquecer resultado)
        document_metadata = get_document_by_s3_key(document_image_key)
        
        # STEP 4: Preprocessing de imagen de usuario
        processed_user_bytes, error = image_processor.process_image(user_image_bytes, user_image_key)
        if error:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='USER_IMAGE_PROCESSING_ERROR',
                validation_mode='DIRECT_COMPARE_BY_IMAGE_KEY',
                document_image_key=document_image_key,
                error=f'User image preprocessing failed: {error}'
            )
        
        # STEP 5: Validar cara en imagen de usuario
        face_detection = rekognition_client.detect_faces(processed_user_bytes)
        if not face_detection['success'] or face_detection['face_count'] == 0:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='NO_FACE_IN_USER_IMAGE',
                validation_mode='DIRECT_COMPARE_BY_IMAGE_KEY',
                document_image_key=document_image_key,
                error='No faces detected in user photo'
            )
        
        # STEP 6: CompareFaces directo
        logger.info(f"Performing direct comparison with threshold {DIRECT_COMPARE_THRESHOLD}")
        
        comparison_result = rekognition_client.compare_faces(
            processed_user_bytes,
            document_image_bytes,
            threshold=DIRECT_COMPARE_THRESHOLD
        )
        
        if not comparison_result['success']:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='COMPARISON_ERROR',
                validation_mode='DIRECT_COMPARE_BY_IMAGE_KEY',
                document_image_key=document_image_key,
                error=f'CompareFaces failed: {comparison_result["error"]}'
            )
        
        # STEP 7: Evaluar resultado
        if comparison_result['match_found']:
            confidence = comparison_result['similarity']
            
            if confidence >= 95:
                status = 'DIRECT_MATCH_HIGH_CONFIDENCE'
            elif confidence >= 85:
                status = 'DIRECT_MATCH_CONFIRMED'
            elif confidence >= 75:
                status = 'DIRECT_MATCH_MODERATE'
            else:
                status = 'DIRECT_MATCH_LOW_CONFIDENCE'
                
            logger.info(f"Direct comparison successful: {confidence:.1f}% similarity")
        else:
            status = 'DIRECT_NO_MATCH'
            confidence = 0
            logger.info(f"Direct comparison: No match found")
        
        # STEP 8: Almacenar resultado
        return store_validation_result(
            comparison_id, user_image_key, start_time,
            status=status,
            validation_mode='DIRECT_COMPARE_BY_IMAGE_KEY',
            document_image_key=document_image_key,
            matched_face_id=document_metadata.get('face_id') if document_metadata else None,
            confidence_score=Decimal(str(confidence)),
            person_name=document_metadata.get('person_name') if document_metadata else extract_person_from_filename(document_image_key),
            target_document_id=document_metadata.get('document_id') if document_metadata else None,
            direct_comparison_threshold=Decimal(str(DIRECT_COMPARE_THRESHOLD)),
            candidates_evaluated=1
        )
        
    except Exception as e:
        logger.error(f"Error in direct comparison by image key {user_image_key}: {str(e)}")
        return store_validation_result(
            comparison_id, user_image_key, start_time,
            status='ERROR',
            validation_mode='DIRECT_COMPARE_BY_IMAGE_KEY',
            document_image_key=document_image_key,
            error=str(e)
        )

def validate_direct_compare_by_document_id(user_image_key: str, target_document_id: str, start_time: float) -> dict:
    """
    Modo directo usando target_document_id (método original)
    """
    comparison_id = generate_comparison_id()
    logger.info(f"🎯 DIRECT COMPARE BY DOCUMENT ID: {user_image_key} vs {target_document_id}")
    
    try:
        # STEP 1: Descargar imagen de usuario
        bucket_name = os.environ['USER_PHOTOS_BUCKET']
        response = s3_client.get_object(Bucket=bucket_name, Key=user_image_key)
        user_image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded user photo {user_image_key}: {len(user_image_bytes)} bytes")
        
        # STEP 2: Obtener metadatos del documento objetivo
        target_document = get_document_by_id(target_document_id)
        if not target_document:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='TARGET_DOCUMENT_NOT_FOUND',
                validation_mode='DIRECT_COMPARE_BY_DOCUMENT_ID',
                target_document_id=target_document_id,
                error=f'Document not found: {target_document_id}'
            )
        
        # STEP 3: Descargar imagen del documento objetivo
        try:
            doc_response = s3_client.get_object(
                Bucket=DOCUMENTS_BUCKET, 
                Key=target_document['s3_key']
            )
            document_image_bytes = doc_response['Body'].read()
            logger.info(f"Downloaded target document: {len(document_image_bytes)} bytes")
        except Exception as e:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='TARGET_DOCUMENT_ACCESS_ERROR',
                validation_mode='DIRECT_COMPARE_BY_DOCUMENT_ID',
                target_document_id=target_document_id,
                error=f'Failed to download target document: {str(e)}'
            )
        
        # STEP 4: Preprocessing de imagen de usuario
        processed_user_bytes, error = image_processor.process_image(user_image_bytes, user_image_key)
        if error:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='USER_IMAGE_PROCESSING_ERROR',
                validation_mode='DIRECT_COMPARE_BY_DOCUMENT_ID',
                target_document_id=target_document_id,
                error=f'User image preprocessing failed: {error}'
            )
        
        # STEP 5: Validar cara en imagen de usuario
        face_detection = rekognition_client.detect_faces(processed_user_bytes)
        if not face_detection['success'] or face_detection['face_count'] == 0:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='NO_FACE_IN_USER_IMAGE',
                validation_mode='DIRECT_COMPARE_BY_DOCUMENT_ID',
                target_document_id=target_document_id,
                error='No faces detected in user photo'
            )
        
        # STEP 6: CompareFaces directo
        logger.info(f"Performing direct comparison with threshold {DIRECT_COMPARE_THRESHOLD}")
        
        comparison_result = rekognition_client.compare_faces(
            processed_user_bytes,
            document_image_bytes,
            threshold=DIRECT_COMPARE_THRESHOLD
        )
        
        if not comparison_result['success']:
            return store_validation_result(
                comparison_id, user_image_key, start_time,
                status='COMPARISON_ERROR',
                validation_mode='DIRECT_COMPARE_BY_DOCUMENT_ID',
                target_document_id=target_document_id,
                error=f'CompareFaces failed: {comparison_result["error"]}'
            )
        
        # STEP 7: Evaluar resultado
        if comparison_result['match_found']:
            confidence = comparison_result['similarity']
            
            if confidence >= 95:
                status = 'DIRECT_MATCH_HIGH_CONFIDENCE'
            elif confidence >= 85:
                status = 'DIRECT_MATCH_CONFIRMED'
            elif confidence >= 75:
                status = 'DIRECT_MATCH_MODERATE'
            else:
                status = 'DIRECT_MATCH_LOW_CONFIDENCE'
                
            logger.info(f"Direct comparison successful: {confidence:.1f}% similarity")
        else:
            status = 'DIRECT_NO_MATCH'
            confidence = 0
            logger.info(f"Direct comparison: No match found")
        
        # STEP 8: Almacenar resultado
        return store_validation_result(
            comparison_id, user_image_key, start_time,
            status=status,
            validation_mode='DIRECT_COMPARE_BY_DOCUMENT_ID',
            target_document_id=target_document_id,
            matched_face_id=target_document.get('face_id'),
            confidence_score=Decimal(str(confidence)),
            person_name=target_document.get('person_name'),
            document_image_key=target_document.get('s3_key'),
            direct_comparison_threshold=Decimal(str(DIRECT_COMPARE_THRESHOLD)),
            candidates_evaluated=1
        )
        
    except Exception as e:
        logger.error(f"Error in direct comparison by document ID {user_image_key}: {str(e)}")
        return store_validation_result(
            comparison_id, user_image_key, start_time,
            status='ERROR',
            validation_mode='DIRECT_COMPARE_BY_DOCUMENT_ID',
            target_document_id=target_document_id,
            error=str(e)
        )

def validate_hybrid_mode(s3_key: str, start_time: float) -> dict:
    """
    MODO HÍBRIDO: SearchFacesByImage + CompareFaces (implementación original)
    """
    comparison_id = generate_comparison_id()
    logger.info(f"🔍 HYBRID MODE: {s3_key}")
    
    try:
        # STEP 1: Descargar imagen de usuario
        bucket_name = os.environ['USER_PHOTOS_BUCKET']
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        user_image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded user photo {s3_key}: {len(user_image_bytes)} bytes")
        
        # STEP 2: Preprocessing mínimo
        processed_bytes, error = image_processor.process_image(user_image_bytes, s3_key)
        if error:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='PROCESSING_ERROR',
                validation_mode='HYBRID',
                error=f'Preprocessing failed: {error}'
            )
        
        # STEP 3: Validar que hay al menos una cara
        face_detection = rekognition_client.detect_faces(processed_bytes)
        if not face_detection['success']:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='NO_FACE_DETECTED',
                validation_mode='HYBRID',
                error=f'Face detection failed: {face_detection["error"]}'
            )
        
        if face_detection['face_count'] == 0:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='NO_FACE_DETECTED',
                validation_mode='HYBRID',
                error='No faces detected in user photo'
            )
        
        # STEP 4: Buscar caras similares en colección
        search_result = rekognition_client.search_faces_by_image(
            processed_bytes,
            threshold=75,
            max_faces=5
        )
        
        if not search_result['success']:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='SEARCH_ERROR',
                validation_mode='HYBRID',
                error=f'Search failed: {search_result["error"]}'
            )
        
        if not search_result['face_matches']:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='NO_MATCH_FOUND',
                validation_mode='HYBRID',
                confidence_score=Decimal('0'),
                search_confidence=Decimal('0')
            )
        
        # STEP 5: CompareFaces con mejores candidatos
        best_match = None
        best_confidence = 0
        candidates_evaluated = 0
        
        for face_match in search_result['face_matches'][:3]:
            candidates_evaluated += 1
            face_id = face_match['Face']['FaceId']
            search_confidence = face_match['Similarity']
            
            logger.info(f"Evaluating candidate {face_id} with search confidence {search_confidence:.1f}%")
            
            document_metadata = get_document_by_face_id(face_id)
            if not document_metadata:
                logger.warning(f"No metadata found for face_id: {face_id}")
                continue
            
            try:
                doc_response = s3_client.get_object(
                    Bucket=DOCUMENTS_BUCKET, 
                    Key=document_metadata['s3_key']
                )
                document_image_bytes = doc_response['Body'].read()
            except Exception as e:
                logger.error(f"Failed to download document {document_metadata['s3_key']}: {str(e)}")
                continue
            
            comparison = rekognition_client.compare_faces(
                processed_bytes,
                document_image_bytes,
                threshold=80
            )
            
            if comparison['success'] and comparison['match_found']:
                confidence = comparison['similarity']
                logger.info(f"CompareFaces result: {confidence:.1f}% similarity")
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        'face_id': face_id,
                        'document_metadata': document_metadata,
                        'confidence': confidence,
                        'search_confidence': search_confidence,
                        'comparison_details': comparison
                    }
        
        # STEP 6: Determinar resultado final
        if best_match:
            if best_confidence >= 85:
                status = 'MATCH_CONFIRMED'
            elif best_confidence >= 75:
                status = 'POSSIBLE_MATCH'
            else:
                status = 'LOW_CONFIDENCE_MATCH'
        else:
            status = 'NO_STRONG_MATCH'
        
        # STEP 7: Almacenar resultado
        return store_validation_result(
            comparison_id, s3_key, start_time,
            status=status,
            validation_mode='HYBRID',
            matched_face_id=best_match['face_id'] if best_match else None,
            confidence_score=Decimal(str(best_confidence)),
            search_confidence=Decimal(str(best_match['search_confidence'])) if best_match else Decimal('0'),
            person_name=best_match['document_metadata']['person_name'] if best_match else None,
            document_image_key=best_match['document_metadata']['s3_key'] if best_match else None,
            candidates_evaluated=candidates_evaluated
        )
        
    except Exception as e:
        logger.error(f"Error in hybrid validation {s3_key}: {str(e)}")
        return store_validation_result(
            comparison_id, s3_key, start_time,
            status='ERROR',
            validation_mode='HYBRID',
            error=str(e)
        )

def get_document_by_face_id(face_id: str) -> dict:
    """Obtener metadatos de documento por face_id"""
    try:
        response = documents_table.query(
            IndexName='face-id-index',
            KeyConditionExpression='face_id = :face_id',
            ExpressionAttributeValues={':face_id': face_id}
        )
        
        if response['Items']:
            return response['Items'][0]
        return None
        
    except Exception as e:
        logger.error(f"Error querying document by face_id {face_id}: {str(e)}")
        return None

def get_document_by_id(document_id: str) -> dict:
    """Obtener metadatos de documento por document_id"""
    try:
        response = documents_table.get_item(
            Key={'document_id': document_id}
        )
        
        if 'Item' in response:
            return response['Item']
        return None
        
    except Exception as e:
        logger.error(f"Error getting document {document_id}: {str(e)}")
        return None

def get_document_by_s3_key(s3_key: str) -> dict:
    """
    NEW: Obtener metadatos de documento por s3_key
    """
    try:
        response = documents_table.scan(
            FilterExpression='s3_key = :key',
            ExpressionAttributeValues={':key': s3_key}
        )
        
        if response['Items']:
            return response['Items'][0]
        return None
        
    except Exception as e:
        logger.error(f"Error querying document by s3_key {s3_key}: {str(e)}")
        return None

def extract_person_from_filename(filename: str) -> str:
    """
    NEW: Extraer nombre de persona del nombre del archivo
    """
    try:
        base_name = os.path.splitext(os.path.basename(filename))[0]
        # Remover sufijos comunes de documentos
        for suffix in ['_dni', '_cedula', '_passport', '_license', '_documento', '_doc']:
            base_name = base_name.replace(suffix, '')
        
        # Convertir a formato legible
        name = base_name.replace('_', ' ').replace('-', ' ')
        return ' '.join(word.capitalize() for word in name.split())
    except:
        return 'Unknown'

def extract_target_document_from_key(s3_key: str) -> str:
    """Extraer document_id objetivo del nombre del archivo (implementación original)"""
    try:
        filename = os.path.basename(s3_key)
        base_name = os.path.splitext(filename)[0]
        
        if '_validation' in base_name:
            person_identifier = base_name.replace('_validation', '')
        elif '_verify' in base_name:
            person_identifier = base_name.replace('_verify', '')
        else:
            person_identifier = base_name
        
        try:
            response = documents_table.query(
                IndexName='person-name-index',
                KeyConditionExpression='person_name = :name',
                ExpressionAttributeValues={':name': person_identifier.replace('_', ' ').title()}
            )
            
            if response['Items']:
                return response['Items'][0]['document_id']
                
        except Exception as e:
            logger.warning(f"Error searching by person name: {e}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting target document from {s3_key}: {e}")
        return None

def store_validation_result(comparison_id: str, user_image_key: str, start_time: float, **kwargs) -> dict:
    """Almacenar resultado de validación en DynamoDB"""
    processing_time = (time.time() - start_time) * 1000
    timestamp = datetime.utcnow().isoformat()
    
    ttl = int(time.time()) + (365 * 24 * 60 * 60)
    
    # Para DynamoDB: convertir floats a Decimal
    processed_kwargs_for_db = {}
    # Para respuesta JSON: mantener como float
    processed_kwargs_for_response = {}
    
    for key, value in kwargs.items():
        if isinstance(value, float):
            processed_kwargs_for_db[key] = Decimal(str(value))
            processed_kwargs_for_response[key] = value  # Mantener como float
        else:
            processed_kwargs_for_db[key] = value
            processed_kwargs_for_response[key] = value
    
    # Item para DynamoDB (con Decimals)
    item_for_db = {
        'comparison_id': comparison_id,
        'timestamp': timestamp,
        'user_image_key': user_image_key,
        'processing_time_ms': int(processing_time),
        'ttl': ttl,
        **processed_kwargs_for_db
    }
    
    # Item para respuesta JSON (con floats)
    item_for_response = {
        'comparison_id': comparison_id,
        'processing_time_ms': int(processing_time),
        **processed_kwargs_for_response
    }
    
    try:
        results_table.put_item(Item=item_for_db)
        logger.info(f"Stored validation result: {comparison_id}")
        
        return item_for_response
        
    except Exception as e:
        logger.error(f"Error storing result: {str(e)}")
        return {
            'comparison_id': comparison_id,
            'status': 'STORAGE_ERROR',
            'error': str(e)
        }

def generate_comparison_id() -> str:
    """Generar ID único para comparación"""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"comp_{timestamp}_{unique_id}"