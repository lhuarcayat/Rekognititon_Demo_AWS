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
VALIDATION_MODE = os.environ.get('VALIDATION_MODE', 'DIRECT_COMPARE')  # HYBRID, DIRECT_COMPARE
DIRECT_COMPARE_THRESHOLD = float(os.environ.get('DIRECT_COMPARE_THRESHOLD', '90.0'))

# Clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
results_table = dynamodb.Table(COMPARISON_RESULTS_TABLE)
documents_table = dynamodb.Table(INDEXED_DOCUMENTS_TABLE)

# Processors
image_processor = MinimalImageProcessor()
rekognition_client = RekognitionClient(COLLECTION_ID)

def lambda_handler(event, context):
    """
    Handler principal para validar fotos de usuarios
    Supports two validation modes:
    - HYBRID: SearchFacesByImage + CompareFaces (current implementation)
    - DIRECT_COMPARE: Direct CompareFaces only
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    logger.info(f"Validation mode: {VALIDATION_MODE}")
    
    start_time = time.time()
    
    try:
        # Handle manual invocation with specific mode
        if 'validation_mode' in event:
            validation_mode = event['validation_mode']
            user_image_key = event.get('user_image_key')
            target_document_id = event.get('target_document_id')  # For direct compare
            
            logger.info(f"Manual invocation - Mode: {validation_mode}, Image: {user_image_key}")
            
            if validation_mode == 'DIRECT_COMPARE' and target_document_id:
                result = validate_direct_compare(user_image_key, target_document_id, start_time)
            elif validation_mode == 'HYBRID':
                result = validate_hybrid_mode(user_image_key, start_time)
            else:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid validation mode or missing parameters',
                        'supported_modes': ['HYBRID', 'DIRECT_COMPARE'],
                        'required_for_direct': ['user_image_key', 'target_document_id']
                    })
                }
            
            return {
                'statusCode': 200,
                'body': json.dumps(result)
            }
        
        # Handle S3 events (automatic validation)
        for record in event['Records']:
            if record['eventSource'] == 'aws:s3':
                bucket_name = record['s3']['bucket']['name']
                s3_key = record['s3']['object']['key']
                
                logger.info(f"Processing user photo: {s3_key}")
                
                # Use configured validation mode for S3 events
                if VALIDATION_MODE == 'DIRECT_COMPARE':
                    # For automatic validation, we need to determine target document
                    # This could be based on filename, user context, etc.
                    target_document_id = extract_target_document_from_key(s3_key)
                    if target_document_id:
                        result = validate_direct_compare(s3_key, target_document_id, start_time)
                    else:
                        # Fallback to hybrid if no target specified
                        logger.warning(f"No target document found for {s3_key}, falling back to HYBRID mode")
                        result = validate_hybrid_mode(s3_key, start_time)
                else:
                    result = validate_hybrid_mode(s3_key, start_time)
                
                # Log resultado final
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

def validate_hybrid_mode(s3_key: str, start_time: float) -> dict:
    """
    MODO HÍBRIDO: SearchFacesByImage + CompareFaces (implementación actual)
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
            threshold=75,  # Threshold bajo para búsqueda inicial
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
        
        for face_match in search_result['face_matches'][:3]:  # Top 3 candidatos
            candidates_evaluated += 1
            face_id = face_match['Face']['FaceId']
            search_confidence = face_match['Similarity']
            
            logger.info(f"Evaluating candidate {face_id} with search confidence {search_confidence:.1f}%")
            
            # Obtener metadatos del documento
            document_metadata = get_document_by_face_id(face_id)
            if not document_metadata:
                logger.warning(f"No metadata found for face_id: {face_id}")
                continue
            
            # Descargar imagen original del documento
            try:
                doc_response = s3_client.get_object(
                    Bucket=DOCUMENTS_BUCKET, 
                    Key=document_metadata['s3_key']
                )
                document_image_bytes = doc_response['Body'].read()
            except Exception as e:
                logger.error(f"Failed to download document {document_metadata['s3_key']}: {str(e)}")
                continue
            
            # CompareFaces detallado
            comparison = rekognition_client.compare_faces(
                processed_bytes,
                document_image_bytes,
                threshold=90
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
            if best_confidence >= 90:
                status = 'MATCH_CONFIRMED'
            elif best_confidence >= 80:
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

def validate_direct_compare(s3_key: str, target_document_id: str, start_time: float) -> dict:
    """
    MODO DIRECTO: CompareFaces directamente con documento específico
    """
    comparison_id = generate_comparison_id()
    logger.info(f"🎯 DIRECT COMPARE MODE: {s3_key} vs {target_document_id}")
    
    try:
        # STEP 1: Descargar imagen de usuario
        bucket_name = os.environ['USER_PHOTOS_BUCKET']
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        user_image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded user photo {s3_key}: {len(user_image_bytes)} bytes")
        
        # STEP 2: Obtener metadatos del documento objetivo
        target_document = get_document_by_id(target_document_id)
        if not target_document:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='TARGET_DOCUMENT_NOT_FOUND',
                validation_mode='DIRECT_COMPARE',
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
                comparison_id, s3_key, start_time,
                status='TARGET_DOCUMENT_ACCESS_ERROR',
                validation_mode='DIRECT_COMPARE',
                target_document_id=target_document_id,
                error=f'Failed to download target document: {str(e)}'
            )
        
        # STEP 4: Preprocessing de imagen de usuario
        processed_user_bytes, error = image_processor.process_image(user_image_bytes, s3_key)
        if error:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='USER_IMAGE_PROCESSING_ERROR',
                validation_mode='DIRECT_COMPARE',
                target_document_id=target_document_id,
                error=f'User image preprocessing failed: {error}'
            )
        
        # STEP 5: Validar cara en imagen de usuario
        face_detection = rekognition_client.detect_faces(processed_user_bytes)
        if not face_detection['success'] or face_detection['face_count'] == 0:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='NO_FACE_IN_USER_IMAGE',
                validation_mode='DIRECT_COMPARE',
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
                comparison_id, s3_key, start_time,
                status='COMPARISON_ERROR',
                validation_mode='DIRECT_COMPARE',
                target_document_id=target_document_id,
                error=f'CompareFaces failed: {comparison_result["error"]}'
            )
        
        # STEP 7: Evaluar resultado
        if comparison_result['match_found']:
            confidence = comparison_result['similarity']
            
            if confidence >= 95:
                status = 'DIRECT_MATCH_HIGH_CONFIDENCE'
            elif confidence >= 90:
                status = 'DIRECT_MATCH_CONFIRMED'
            else:
                status = 'DIRECT_MATCH_LOW_CONFIDENCE'
                
            logger.info(f"Direct comparison successful: {confidence:.1f}% similarity")
        else:
            status = 'DIRECT_NO_MATCH'
            confidence = 0
            logger.info(f"Direct comparison: No match found")
        
        # STEP 8: Almacenar resultado
        return store_validation_result(
            comparison_id, s3_key, start_time,
            status=status,
            validation_mode='DIRECT_COMPARE',
            target_document_id=target_document_id,
            matched_face_id=target_document.get('face_id'),
            confidence_score=Decimal(str(confidence)),
            person_name=target_document.get('person_name'),
            document_image_key=target_document.get('s3_key'),
            direct_comparison_threshold=Decimal(str(DIRECT_COMPARE_THRESHOLD)),
            candidates_evaluated=1  # Solo se evaluó un candidato
        )
        
    except Exception as e:
        logger.error(f"Error in direct comparison {s3_key}: {str(e)}")
        return store_validation_result(
            comparison_id, s3_key, start_time,
            status='ERROR',
            validation_mode='DIRECT_COMPARE',
            target_document_id=target_document_id,
            error=str(e)
        )

def get_document_by_face_id(face_id: str) -> dict:
    """
    Obtener metadatos de documento por face_id
    """
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
    """
    Obtener metadatos de documento por document_id
    """
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

def extract_target_document_from_key(s3_key: str) -> str:
    """
    Extraer document_id objetivo del nombre del archivo
    Ejemplo: "user_photos/juan_perez_validation.jpg" -> buscar documento de "juan_perez"
    """
    try:
        # Extraer nombre base del archivo
        filename = os.path.basename(s3_key)
        base_name = os.path.splitext(filename)[0]
        
        # Buscar patterns que indiquen el documento objetivo
        # Ejemplo: "juan_perez_validation" -> "juan_perez"
        if '_validation' in base_name:
            person_identifier = base_name.replace('_validation', '')
        elif '_verify' in base_name:
            person_identifier = base_name.replace('_verify', '')
        else:
            person_identifier = base_name
        
        # Buscar documento por person_name
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
        
        # Si no encuentra por nombre, retornar None para usar modo híbrido
        return None
        
    except Exception as e:
        logger.error(f"Error extracting target document from {s3_key}: {e}")
        return None

def store_validation_result(comparison_id: str, user_image_key: str, start_time: float, **kwargs) -> dict:
    """
    Almacenar resultado de validación en DynamoDB
    """
    processing_time = (time.time() - start_time) * 1000
    timestamp = datetime.utcnow().isoformat()
    
    # TTL: 1 año desde ahora
    ttl = int(time.time()) + (365 * 24 * 60 * 60)
    
    # Convert floats to Decimal for DynamoDB
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