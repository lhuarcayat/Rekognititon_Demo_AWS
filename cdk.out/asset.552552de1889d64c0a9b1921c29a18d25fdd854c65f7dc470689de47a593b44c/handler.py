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
USER_PHOTOS_BUCKET = os.environ['USER_PHOTOS_BUCKET']
DOCUMENT_INDEXER_FUNCTION = os.environ.get('DOCUMENT_INDEXER_FUNCTION', 'rekognition-poc-document-indexer')

# Clients
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')
rekognition = boto3.client('rekognition')  # Cliente directo para liveness
dynamodb = boto3.resource('dynamodb')
results_table = dynamodb.Table(COMPARISON_RESULTS_TABLE)
documents_table = dynamodb.Table(INDEXED_DOCUMENTS_TABLE)

# Processors
image_processor = MinimalImageProcessor()
rekognition_client = RekognitionClient(COLLECTION_ID)

def lambda_handler(event, context):
    """
    Handler actualizado para validación con Face Liveness
    Triggered por S3 events cuando se sube archivo marcador al bucket user-photos
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    start_time = time.time()
    
    try:
        # Procesar eventos S3
        for record in event['Records']:
            if record['eventSource'] == 'aws:s3':
                bucket_name = record['s3']['bucket']['name']
                trigger_file_key = record['s3']['object']['key']
                
                logger.info(f"Processing trigger file with liveness support: {trigger_file_key}")
                
                # VERIFICAR SI ES ARCHIVO DE LIVENESS
                if is_liveness_trigger_file(trigger_file_key):
                    result = validate_liveness_session(trigger_file_key, start_time)
                else:
                    # Mantener compatibilidad con flujo original (foto manual)
                    result = validate_user_photo_with_specific_errors(trigger_file_key, start_time)
                
                # Log resultado final
                processing_time = (time.time() - start_time) * 1000
                logger.info(f"Validation completed for {trigger_file_key}: {result['status']} in {processing_time:.0f}ms")
        
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

# ============================================
# FACE LIVENESS FUNCTIONS
# ============================================

def is_liveness_trigger_file(file_key: str) -> bool:
    """
    Verificar si el archivo es un trigger de liveness session
    Formato: liveness-session-{sessionId}-{timestamp}.jpg
    """
    try:
        filename = os.path.basename(file_key)
        return filename.startswith('liveness-session-')
    except:
        return False

def validate_liveness_session(trigger_file_key: str, start_time: float) -> dict:
    """
    NUEVA FUNCIÓN: Validación usando liveness session en lugar de foto subida
    """
    comparison_id = generate_comparison_id()
    
    try:
        # PASO 1: Extraer session ID desde el nombre del archivo
        session_id = extract_session_id_from_trigger_file(trigger_file_key)
        if not session_id:
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='INVALID_TRIGGER_FILE',
                error='Cannot extract session ID from trigger file',
                error_type='FILENAME_ERROR',
                allow_retry=False
            )
        
        logger.info(f"Processing liveness session: {session_id}")
        
        # PASO 2: Obtener reference image desde liveness session
        try:
            reference_image_bytes, liveness_confidence = get_reference_image_from_liveness(session_id)
            logger.info(f"Reference image obtained, liveness confidence: {liveness_confidence:.1f}%")
            
        except Exception as liveness_error:
            logger.error(f"Failed to get reference image: {str(liveness_error)}")
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='LIVENESS_FAILED',
                error=f'Liveness processing failed: {str(liveness_error)}',
                error_type='LIVENESS_ERROR',
                allow_retry=True,
                liveness_session_id=session_id
            )
        
        # PASO 3: Verificar confidence de liveness (threshold más alto)
        if liveness_confidence < 95:  # Threshold más alto para liveness
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='LOW_LIVENESS_CONFIDENCE',
                error=f'Liveness confidence too low: {liveness_confidence:.1f}%',
                error_type='LOW_LIVENESS_CONFIDENCE',
                confidence_score=Decimal(str(liveness_confidence)),
                allow_retry=True,
                liveness_session_id=session_id
            )
        
        # PASO 4: Extraer info del documento desde session metadata o filename
        document_info = extract_document_info_from_session_metadata(session_id)
        if not document_info:
            # Fallback: usar info almacenada en formData global o filename patterns
            document_info = extract_document_info_fallback()
            
        if not document_info:
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='DOCUMENT_INFO_MISSING',
                error='Cannot determine document information',
                error_type='METADATA_ERROR',
                allow_retry=False,
                liveness_session_id=session_id
            )
        
        tipo_documento = document_info['tipo_documento']
        numero_documento = document_info['numero_documento']
        
        # PASO 5: Verificar que el documento correspondiente existe
        document_key = f"{tipo_documento}-{numero_documento}.jpg"
        
        try:
            s3_client.head_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
            logger.info(f"Found corresponding document: {document_key}")
        except s3_client.exceptions.NoSuchKey:
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='DOCUMENT_NOT_FOUND',
                error=f'Document not found: {document_key}',
                error_type='DOCUMENT_MISSING',
                allow_retry=False,
                liveness_session_id=session_id
            )
        
        # PASO 6: Descargar documento
        doc_response = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=document_key)
        document_image_bytes = doc_response['Body'].read()
        logger.info(f"Downloaded document {document_key}: {len(document_image_bytes)} bytes")
        
        # PASO 7: Procesar imágenes
        processed_ref_bytes, ref_error = image_processor.process_image(
            reference_image_bytes, 
            f"liveness-{session_id}"
        )
        if ref_error:
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='REFERENCE_PROCESSING_ERROR',
                error=f'Reference image processing failed: {ref_error}',
                error_type='IMAGE_PROCESSING_ERROR',
                allow_retry=True,
                liveness_session_id=session_id
            )
        
        processed_doc_bytes, doc_error = image_processor.process_image(document_image_bytes, document_key)
        if doc_error:
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='DOCUMENT_PROCESSING_ERROR',
                error=f'Document processing failed: {doc_error}',
                error_type='IMAGE_PROCESSING_ERROR',
                allow_retry=True,
                liveness_session_id=session_id
            )
        
        # PASO 8: CompareFaces (reference image vs documento)
        logger.info("Comparing liveness reference image with document...")
        
        comparison = rekognition_client.compare_faces(
            processed_ref_bytes,  # Source: reference image de liveness
            processed_doc_bytes,  # Target: documento
            threshold=80.0
        )
        
        if not comparison['success']:
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='COMPARISON_FAILED',
                error=f'Face comparison failed: {comparison["error"]}',
                error_type='COMPARISON_ERROR',
                allow_retry=True,
                liveness_session_id=session_id
            )
        
        # PASO 9: Evaluar resultados
        if comparison['match_found']:
            similarity = comparison['similarity']
            logger.info(f"Match found: {similarity:.1f}% similarity, {liveness_confidence:.1f}% liveness")
            
            if similarity >= 90:  # Threshold alto para liveness
                # Indexar document si es exitoso y no está ya indexado
                person_name = extract_person_name(document_key)
                document_indexed = False
                
                # Verificar si ya está indexado
                existing_document = check_document_already_indexed(document_key)
                
                if not existing_document:
                    logger.info(f"Indexing document for first time: {document_key}")
                    index_result = await_index_document(document_key)
                    document_indexed = index_result and index_result.get('success')
                    logger.info(f"Document indexing result: {document_indexed}")
                else:
                    logger.info(f"Document already indexed: {document_key}")
                    person_name = existing_document.get('person_name', person_name)
                
                return store_validation_result(
                    comparison_id, trigger_file_key, start_time,
                    status='MATCH_CONFIRMED',
                    confidence_score=Decimal(str(liveness_confidence)),
                    similarity_score=Decimal(str(similarity)),
                    person_name=person_name,
                    document_image_key=document_key,
                    document_indexed=document_indexed,
                    comparison_method='LIVENESS_COMPARE',
                    liveness_session_id=session_id
                )
            else:
                return store_validation_result(
                    comparison_id, trigger_file_key, start_time,
                    status='LOW_SIMILARITY',
                    error=f'Low similarity: {similarity:.1f}%',
                    error_type='LOW_SIMILARITY',
                    confidence_score=Decimal(str(liveness_confidence)),
                    similarity_score=Decimal(str(similarity)),
                    allow_retry=True,
                    liveness_session_id=session_id
                )
        else:
            return store_validation_result(
                comparison_id, trigger_file_key, start_time,
                status='NO_FACE_MATCH',
                error='No match between liveness and document',
                error_type='NO_MATCH_FOUND',
                confidence_score=Decimal(str(liveness_confidence)),
                allow_retry=True,
                liveness_session_id=session_id
            )
        
    except Exception as e:
        logger.error(f"Error validating liveness session {trigger_file_key}: {str(e)}")
        return store_validation_result(
            comparison_id, trigger_file_key, start_time,
            status='SYSTEM_ERROR',
            error=str(e),
            error_type='PROCESSING_ERROR',
            allow_retry=True,
            liveness_session_id=session_id if 'session_id' in locals() else None
        )

def extract_session_id_from_trigger_file(trigger_file_key: str) -> str:
    """
    Extraer session ID desde el nombre del archivo trigger
    Formato: liveness-session-{sessionId}-{timestamp}.jpg
    """
    try:
        filename = os.path.basename(trigger_file_key)
        base_name = os.path.splitext(filename)[0]
        
        # Patrón: liveness-session-{sessionId}-{timestamp}
        if base_name.startswith('liveness-session-'):
            parts = base_name.split('-')
            if len(parts) >= 3:
                # Extraer todo entre 'liveness-session-' y el último '-{timestamp}'
                session_id = '-'.join(parts[2:-1])  # Todo menos 'liveness', 'session' y timestamp
                logger.info(f"Extracted session ID: {session_id}")
                return session_id
        
        # Fallback: buscar patrón de session ID AWS (formato UUID)
        session_pattern = r'([a-f0-9-]{36})'  # UUID format
        match = re.search(session_pattern, base_name)
        if match:
            return match.group(1)
        
        logger.error(f"Cannot extract session ID from: {trigger_file_key}")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting session ID: {str(e)}")
        return None

def get_reference_image_from_liveness(session_id: str) -> tuple:
    """
    Obtener reference image desde sesión de liveness
    Returns: (image_bytes, confidence_score)
    """
    try:
        logger.info(f"Getting liveness results for session: {session_id}")
        
        results = rekognition.get_face_liveness_session_results(
            SessionId=session_id
        )
        
        logger.info(f"Liveness session status: {results['Status']}")
        logger.info(f"Liveness confidence: {results.get('Confidence', 0)}")
        
        if results['Status'] != 'SUCCEEDED':
            raise Exception(f"Liveness session failed: {results['Status']}")
        
        reference_image = results.get('ReferenceImage')
        if not reference_image:
            raise Exception('No reference image available in liveness results')
        
        confidence = float(results.get('Confidence', 0))
        
        # Opción 1: Bytes directos (mejor performance)
        if reference_image.get('Bytes'):
            logger.info("Using direct bytes from liveness result")
            return reference_image['Bytes'], confidence
        
        # Opción 2: Descargar desde S3 (si está allí)
        if reference_image.get('S3Object'):
            s3_obj = reference_image['S3Object']
            logger.info(f"Downloading reference image from S3: {s3_obj['Bucket']}/{s3_obj['Name']}")
            
            response = s3_client.get_object(
                Bucket=s3_obj['Bucket'],
                Key=s3_obj['Name']
            )
            return response['Body'].read(), confidence
        
        raise Exception('Reference image not available in bytes or S3')
        
    except Exception as e:
        logger.error(f"Error getting reference image from liveness: {str(e)}")
        raise e

def extract_document_info_from_session_metadata(session_id: str) -> dict:
    """
    Extraer info del documento desde metadata de la sesión
    Por ahora retorna None para usar fallback
    """
    # TODO: En producción, implementar lookup desde DynamoDB session metadata
    return None

def extract_document_info_fallback() -> dict:
    """
    Fallback para obtener información del documento
    """
    # En una implementación real, esto podría venir de:
    # 1. Session storage en DynamoDB
    # 2. Context global de la aplicación
    # 3. Headers de la request
    
    # Por ahora, usar valores por defecto para testing
    return {
        'tipo_documento': 'DNI',
        'numero_documento': '12345678'
    }

def validate_user_photo_with_specific_errors(trigger_file_key: str, start_time: float) -> dict:
    """
    Validación original para fotos manuales (mantener compatibilidad)
    """
    comparison_id = generate_comparison_id()
    
    # Implementación simplificada para mantener compatibilidad
    return store_validation_result(
        comparison_id, trigger_file_key, start_time,
        status='LEGACY_MODE_NOT_IMPLEMENTED',
        error='Use liveness validation instead',
        error_type='DEPRECATED_METHOD',
        allow_retry=False
    )

def check_document_already_indexed(document_key: str) -> dict:
    """
    Verificar si un documento ya fue indexado en DynamoDB
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
        logger.error(f"Error checking document {document_key}: {str(e)}")
        return None

def await_index_document(document_key: str) -> dict:
    """
    Invocar lambda de indexación de documento
    """
    try:
        payload = {
            'documents': [document_key]
        }
        
        response = lambda_client.invoke(
            FunctionName=DOCUMENT_INDEXER_FUNCTION,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        return json.loads(result['body']) if 'body' in result else result
        
    except Exception as e:
        logger.error(f"Error invoking document indexer: {str(e)}")
        return {'success': False, 'error': str(e)}

def store_validation_result(comparison_id: str, user_image_key: str, start_time: float, 
                          status: str, confidence_score=None, similarity_score=None, 
                          person_name=None, document_image_key=None, 
                          document_indexed=False, comparison_method='COMPARE_FACES',
                          error=None, error_type=None, allow_retry=True,
                          matched_face_id=None, search_confidence=None,
                          liveness_session_id=None, **kwargs) -> dict:
    """
    Almacenar resultado de validación en DynamoDB
    """
    try:
        processing_time = (time.time() - start_time) * 1000
        timestamp = datetime.utcnow().isoformat()
        
        # Base item
        item = {
            'comparison_id': comparison_id,
            'timestamp': timestamp,
            'user_image_key': user_image_key,
            'status': status,
            'processing_time_ms': Decimal(str(processing_time)),
            'comparison_method': comparison_method,
            'allow_retry': allow_retry,
            'ttl': int((datetime.utcnow().timestamp() + 86400 * 7))  # 7 días TTL
        }
        
        # Campos opcionales
        if confidence_score is not None:
            item['confidence_score'] = confidence_score
        if similarity_score is not None:
            item['similarity'] = similarity_score
        if person_name:
            item['person_name'] = person_name
        if document_image_key:
            item['document_image_key'] = document_image_key
        if matched_face_id:
            item['matched_face_id'] = matched_face_id
        if search_confidence:
            item['search_confidence'] = Decimal(str(search_confidence))
        if error:
            item['error'] = error
        if error_type:
            item['error_type'] = error_type
        if liveness_session_id:
            item['liveness_session_id'] = liveness_session_id
            
        item['document_indexed'] = document_indexed
        
        # Agregar campos adicionales del kwargs
        for key, value in kwargs.items():
            if value is not None:
                item[key] = value
        
        results_table.put_item(Item=item)
        
        logger.info(f"Stored validation result: {comparison_id} - {status}")
        
        return {
            'comparison_id': comparison_id,
            'status': status,
            'processing_time_ms': processing_time
        }
        
    except Exception as e:
        logger.error(f"Error storing validation result: {str(e)}")
        return {
            'comparison_id': comparison_id,
            'status': 'STORAGE_ERROR',
            'error': str(e)
        }

def generate_comparison_id() -> str:
    """Generar ID único para comparación"""
    return str(uuid.uuid4())

def extract_person_name(document_key: str) -> str:
    """Extraer nombre de persona desde el nombre del archivo"""
    try:
        base_name = os.path.splitext(os.path.basename(document_key))[0]
        name = base_name.replace('_', ' ').replace('-', ' ')
        remove_words = ['dni', 'cedula', 'passport', 'documento', 'doc', 'id']
        words = [word for word in name.split() if word.lower() not in remove_words]
        return ' '.join(word.capitalize() for word in words) if words else base_name
    except Exception as e:
        logger.error(f"Error extracting person name from {document_key}: {str(e)}")
        return "Unknown"