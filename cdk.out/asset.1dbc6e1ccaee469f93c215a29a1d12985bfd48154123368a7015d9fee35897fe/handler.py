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
    Triggered por S3 events cuando se sube foto al bucket user-photos
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    start_time = time.time()
    
    try:
        # Procesar eventos S3
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
        
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }

def validate_user_photo(s3_key: str, start_time: float) -> dict:
    """
    Validar foto de usuario contra colección de documentos
    """
    comparison_id = generate_comparison_id()
    
    try:
        # STEP 1: Descargar imagen de usuario
        #bucket_name = os.environ.get('USER_PHOTOS_BUCKET', s3_key.split('/')[0])
        bucket_name=os.environ['USER_PHOTOS_BUCKET']
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        user_image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded user photo {s3_key}: {len(user_image_bytes)} bytes")
        
        # STEP 2: Preprocessing mínimo
        processed_bytes, error = image_processor.process_image(user_image_bytes, s3_key)
        if error:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='PROCESSING_ERROR',
                error=f'Preprocessing failed: {error}'
            )
        
        # STEP 3: Validar que hay al menos una cara
        face_detection = rekognition_client.detect_faces(processed_bytes)
        if not face_detection['success']:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='NO_FACE_DETECTED',
                error=f'Face detection failed: {face_detection["error"]}'
            )
        
        if face_detection['face_count'] == 0:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='NO_FACE_DETECTED',
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
                error=f'Search failed: {search_result["error"]}'
            )
        
        if not search_result['face_matches']:
            return store_validation_result(
                comparison_id, s3_key, start_time,
                status='NO_MATCH_FOUND',
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
            matched_face_id=best_match['face_id'] if best_match else None,
            confidence_score=Decimal(str(best_confidence)),
            search_confidence=Decimal(str(best_match['search_confidence'])) if best_match else Decimal('0'),
            person_name=best_match['document_metadata']['person_name'] if best_match else None,
            document_image_key=best_match['document_metadata']['s3_key'] if best_match else None,
            candidates_evaluated=candidates_evaluated
        )
        
    except Exception as e:
        logger.error(f"Error validating {s3_key}: {str(e)}")
        return store_validation_result(
            comparison_id, s3_key, start_time,
            status='ERROR',
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