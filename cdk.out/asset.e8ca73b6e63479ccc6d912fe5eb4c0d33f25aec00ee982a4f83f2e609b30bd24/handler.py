import json
import boto3
import logging
import os
from datetime import datetime
import time

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
COLLECTION_ID = os.environ['COLLECTION_ID']
INDEXED_DOCUMENTS_TABLE = os.environ['INDEXED_DOCUMENTS_TABLE']
COMPARISON_RESULTS_TABLE = os.environ['COMPARISON_RESULTS_TABLE']

# AWS Clients
rekognition_client = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    """
    Función principal para limpiar colección de Rekognition y tablas DynamoDB
    
    Modos soportados:
    1. {"action": "cleanup_all"} - Limpiar todo (colección + tablas)
    2. {"action": "cleanup_collection"} - Solo limpiar colección Rekognition
    3. {"action": "cleanup_tables"} - Solo limpiar tablas DynamoDB
    4. {"action": "status"} - Ver estado actual sin limpiar
    """
    
    logger.info(f"Received cleanup event: {json.dumps(event)}")
    
    start_time = time.time()
    
    try:
        # Determinar acción a ejecutar
        action = event.get('action', 'cleanup_all')
        
        if action == 'cleanup_all':
            return cleanup_all_resources()
            
        elif action == 'cleanup_collection':
            return cleanup_rekognition_collection()
            
        elif action == 'cleanup_tables':
            return cleanup_dynamodb_tables()
            
        elif action == 'status':
            return get_cleanup_status()
            
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid action specified',
                    'supported_actions': ['cleanup_all', 'cleanup_collection', 'cleanup_tables', 'status'],
                    'example': '{"action": "cleanup_all"}'
                })
            }
            
    except Exception as e:
        logger.error(f"Unhandled error in cleanup: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Cleanup failed: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            })
        }

def cleanup_all_resources():
    """
    MODO 1: Limpiar todos los recursos (colección + tablas)
    """
    logger.info("🧹 CLEANUP ALL: Starting complete cleanup process")
    
    start_time = time.time()
    results = {
        'action': 'cleanup_all',
        'timestamp': datetime.utcnow().isoformat(),
        'results': {}
    }
    
    try:
        # STEP 1: Limpiar colección de Rekognition
        logger.info("Step 1: Cleaning Rekognition collection...")
        collection_result = cleanup_rekognition_collection_internal()
        results['results']['rekognition_collection'] = collection_result
        
        # STEP 2: Limpiar tablas DynamoDB
        logger.info("Step 2: Cleaning DynamoDB tables...")
        tables_result = cleanup_dynamodb_tables_internal()
        results['results']['dynamodb_tables'] = tables_result
        
        # STEP 3: Calcular resultados totales
        total_faces_deleted = collection_result.get('faces_deleted', 0)
        total_documents_deleted = tables_result.get('indexed_documents_deleted', 0)
        total_comparisons_deleted = tables_result.get('comparison_results_deleted', 0)
        
        processing_time = (time.time() - start_time) * 1000
        
        success = (collection_result.get('success', False) and 
                  tables_result.get('success', False))
        
        results.update({
            'success': success,
            'processing_time_ms': int(processing_time),
            'summary': {
                'faces_deleted': total_faces_deleted,
                'documents_deleted': total_documents_deleted,
                'comparisons_deleted': total_comparisons_deleted,
                'collection_cleaned': collection_result.get('success', False),
                'tables_cleaned': tables_result.get('success', False)
            }
        })
        
        if success:
            logger.info(f"✅ CLEANUP COMPLETED: {total_faces_deleted} faces, {total_documents_deleted} documents, {total_comparisons_deleted} comparisons deleted in {processing_time:.0f}ms")
        else:
            logger.warning("⚠️ CLEANUP COMPLETED WITH ERRORS - check individual results")
        
        return {
            'statusCode': 200,
            'body': json.dumps(results)
        }
        
    except Exception as e:
        logger.error(f"Error in complete cleanup: {str(e)}")
        results.update({
            'success': False,
            'error': str(e),
            'processing_time_ms': int((time.time() - start_time) * 1000)
        })
        
        return {
            'statusCode': 500,
            'body': json.dumps(results)
        }

def cleanup_rekognition_collection():
    """
    MODO 2: Solo limpiar colección de Rekognition
    """
    logger.info("🎯 CLEANUP COLLECTION: Cleaning Rekognition collection only")
    
    result = cleanup_rekognition_collection_internal()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'action': 'cleanup_collection',
            'timestamp': datetime.utcnow().isoformat(),
            **result
        })
    }

def cleanup_dynamodb_tables():
    """
    MODO 3: Solo limpiar tablas DynamoDB
    """
    logger.info("📊 CLEANUP TABLES: Cleaning DynamoDB tables only")
    
    result = cleanup_dynamodb_tables_internal()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'action': 'cleanup_tables',
            'timestamp': datetime.utcnow().isoformat(),
            **result
        })
    }

def cleanup_rekognition_collection_internal():
    """
    Limpiar colección de Rekognition (función interna)
    """
    start_time = time.time()
    
    try:
        # STEP 1: Verificar si la colección existe
        try:
            collection_info = rekognition_client.describe_collection(CollectionId=COLLECTION_ID)
            initial_face_count = collection_info['FaceCount']
            logger.info(f"Collection {COLLECTION_ID} exists with {initial_face_count} faces")
            
        except rekognition_client.exceptions.ResourceNotFoundException:
            logger.info(f"Collection {COLLECTION_ID} does not exist - nothing to clean")
            return {
                'success': True,
                'faces_deleted': 0,
                'message': 'Collection does not exist',
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }
        
        if initial_face_count == 0:
            logger.info("Collection is already empty")
            return {
                'success': True,
                'faces_deleted': 0,
                'message': 'Collection already empty',
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }
        
        # STEP 2: Obtener todas las caras en la colección
        logger.info("Getting all faces in collection...")
        all_face_ids = []
        
        paginator = rekognition_client.get_paginator('list_faces')
        for page in paginator.paginate(CollectionId=COLLECTION_ID):
            faces = page.get('Faces', [])
            face_ids = [face['FaceId'] for face in faces]
            all_face_ids.extend(face_ids)
        
        logger.info(f"Found {len(all_face_ids)} faces to delete")
        
        # STEP 3: Eliminar caras en lotes (máximo 4096 por llamada)
        faces_deleted = 0
        batch_size = 4096  # Límite de AWS
        
        for i in range(0, len(all_face_ids), batch_size):
            batch = all_face_ids[i:i + batch_size]
            
            try:
                delete_response = rekognition_client.delete_faces(
                    CollectionId=COLLECTION_ID,
                    FaceIds=batch
                )
                
                deleted_faces = delete_response.get('DeletedFaces', [])
                faces_deleted += len(deleted_faces)
                
                logger.info(f"Deleted batch {i//batch_size + 1}: {len(deleted_faces)} faces")
                
            except Exception as e:
                logger.error(f"Error deleting batch {i//batch_size + 1}: {str(e)}")
                # Continuar con el siguiente lote en caso de error
        
        # STEP 4: Verificar limpieza
        final_collection_info = rekognition_client.describe_collection(CollectionId=COLLECTION_ID)
        final_face_count = final_collection_info['FaceCount']
        
        processing_time = (time.time() - start_time) * 1000
        
        success = (final_face_count == 0)
        
        result = {
            'success': success,
            'faces_deleted': faces_deleted,
            'initial_face_count': initial_face_count,
            'final_face_count': final_face_count,
            'collection_id': COLLECTION_ID,
            'processing_time_ms': int(processing_time)
        }
        
        if success:
            logger.info(f"✅ Collection cleanup successful: {faces_deleted} faces deleted")
        else:
            logger.warning(f"⚠️ Collection cleanup incomplete: {final_face_count} faces remain")
        
        return result
        
    except Exception as e:
        logger.error(f"Error cleaning Rekognition collection: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'processing_time_ms': int((time.time() - start_time) * 1000)
        }

def cleanup_dynamodb_tables_internal():
    """
    Limpiar tablas DynamoDB (función interna)
    """
    start_time = time.time()
    
    try:
        results = {}
        
        # STEP 1: Limpiar tabla de documentos indexados
        logger.info("Cleaning indexed documents table...")
        indexed_docs_result = cleanup_table(INDEXED_DOCUMENTS_TABLE, 'document_id')
        results['indexed_documents'] = indexed_docs_result
        
        # STEP 2: Limpiar tabla de resultados de comparación
        logger.info("Cleaning comparison results table...")
        comparison_results_result = cleanup_table(COMPARISON_RESULTS_TABLE, 'comparison_id', 'timestamp')
        results['comparison_results'] = comparison_results_result
        
        # STEP 3: Consolidar resultados
        total_documents_deleted = indexed_docs_result.get('items_deleted', 0)
        total_comparisons_deleted = comparison_results_result.get('items_deleted', 0)
        
        all_successful = (indexed_docs_result.get('success', False) and 
                         comparison_results_result.get('success', False))
        
        processing_time = (time.time() - start_time) * 1000
        
        result = {
            'success': all_successful,
            'indexed_documents_deleted': total_documents_deleted,
            'comparison_results_deleted': total_comparisons_deleted,
            'tables_cleaned': {
                'indexed_documents': indexed_docs_result.get('success', False),
                'comparison_results': comparison_results_result.get('success', False)
            },
            'details': results,
            'processing_time_ms': int(processing_time)
        }
        
        logger.info(f"Tables cleanup: {total_documents_deleted} documents, {total_comparisons_deleted} comparisons deleted")
        
        return result
        
    except Exception as e:
        logger.error(f"Error cleaning DynamoDB tables: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'processing_time_ms': int((time.time() - start_time) * 1000)
        }

def cleanup_table(table_name, partition_key, sort_key=None):
    """
    🔧 FUNCIÓN CORREGIDA: Limpiar una tabla específica de DynamoDB
    """
    try:
        table = dynamodb.Table(table_name)
        
        # STEP 1: Contar elementos iniciales
        scan_response = table.scan(Select='COUNT')
        initial_count = scan_response['Count']
        
        if initial_count == 0:
            logger.info(f"Table {table_name} is already empty")
            return {
                'success': True,
                'items_deleted': 0,
                'message': 'Table already empty'
            }
        
        logger.info(f"Table {table_name} has {initial_count} items to delete")
        
   
        items_deleted = 0

        scan_kwargs = {}
        
        if sort_key == 'timestamp':
            scan_kwargs.update({
                'ProjectionExpression': f'{partition_key}, #ts',
                'ExpressionAttributeNames': {
                    '#ts': 'timestamp'
                }
            })
        elif sort_key:
            scan_kwargs['ProjectionExpression'] = f'{partition_key}, {sort_key}'
        else:
            scan_kwargs['ProjectionExpression'] = partition_key
        

        while True:
            response = table.scan(**scan_kwargs)
            items = response.get('Items', [])
            
            if not items:
                break
            

            with table.batch_writer() as batch:
                for item in items:
                    # Construir clave para eliminación
                    delete_key = {partition_key: item[partition_key]}
                    if sort_key and sort_key in item:
                        delete_key[sort_key] = item[sort_key]
                    
                    # 🔧 FIX 4: Key con K mayúscula (no key)
                    batch.delete_item(Key=delete_key)
                    items_deleted += 1
            
            logger.info(f"Deleted batch from {table_name}: {len(items)} items")
            
            # Si no hay más elementos que escanear, salir
            if 'LastEvaluatedKey' not in response:
                break
            
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        
        # STEP 4: Verificar limpieza
        final_scan = table.scan(Select='COUNT')
        final_count = final_scan['Count']
        
        success = (final_count == 0)
        
        return {
            'success': success,
            'items_deleted': items_deleted,
            'initial_count': initial_count,
            'final_count': final_count,
            'table_name': table_name
        }
        
    except Exception as e:
        logger.error(f"Error cleaning table {table_name}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'table_name': table_name
        }

def get_cleanup_status():
    """
    MODO 4: Obtener estado actual sin limpiar nada
    """
    logger.info("📊 STATUS: Getting current status of resources")
    
    try:
        status = {
            'action': 'status',
            'timestamp': datetime.utcnow().isoformat(),
            'rekognition_collection': {},
            'dynamodb_tables': {}
        }
        
        # STEP 1: Estado de la colección Rekognition
        try:
            collection_info = rekognition_client.describe_collection(CollectionId=COLLECTION_ID)
            status['rekognition_collection'] = {
                'exists': True,
                'face_count': collection_info['FaceCount'],
                'face_model_version': collection_info['FaceModelVersion'],
                'created': collection_info['CreationTimestamp'].isoformat()
            }
        except rekognition_client.exceptions.ResourceNotFoundException:
            status['rekognition_collection'] = {
                'exists': False,
                'face_count': 0
            }
        
        # STEP 2: Estado de las tablas DynamoDB
        for table_name in [INDEXED_DOCUMENTS_TABLE, COMPARISON_RESULTS_TABLE]:
            try:
                table = dynamodb.Table(table_name)
                scan_response = table.scan(Select='COUNT')
                
                status['dynamodb_tables'][table_name] = {
                    'exists': True,
                    'item_count': scan_response['Count']
                }
            except Exception as e:
                status['dynamodb_tables'][table_name] = {
                    'exists': False,
                    'error': str(e)
                }
        
        # STEP 3: Resumen
        total_faces = status['rekognition_collection'].get('face_count', 0)
        total_documents = status['dynamodb_tables'].get(INDEXED_DOCUMENTS_TABLE, {}).get('item_count', 0)
        total_comparisons = status['dynamodb_tables'].get(COMPARISON_RESULTS_TABLE, {}).get('item_count', 0)
        
        status['summary'] = {
            'total_faces': total_faces,
            'total_documents': total_documents,
            'total_comparisons': total_comparisons,
            'needs_cleanup': (total_faces > 0 or total_documents > 0 or total_comparisons > 0)
        }
        
        logger.info(f"Current status: {total_faces} faces, {total_documents} documents, {total_comparisons} comparisons")
        
        return {
            'statusCode': 200,
            'body': json.dumps(status)
        }
        
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Failed to get status: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            })
        }








