import json
import boto3
import logging
import os
from datetime import datetime
import time
logger = logging.getLogger()
logger.setLevel(logging.INFO)

COLLECTION_ID = os.environ['COLLECTION_ID']
INDEXED_DOCUMENTS_TABLE = os.environ['INDEXED_DOCUMENTS_TABLE']
COMPARISON_RESULTS_TABLE = os.environ['COMPARISON_RESULTS_TABLE']

rekognition_client = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    '''
    modos soportados:
    {"action":"cleanup_all"} - Limpiar todo (colección y tablas)
    {"action":"cleanup_collection"} - Limpiar solo la colección
    {"action":"cleanup_tables"} - Limpiar solo las tablas de dynamodb
    {"action":"status"} - Ver estado actual
    '''
    logger.info(f'Received cleanup event: {json.dumps(event)}')
    start_time = time.time()

    try:
        action = event.get('action','cleanup_all')
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
                'statusCode':400,
                'body': json.dumps({
                    'error':'Invalid action specified',
                    'supported_actions':['cleanup_all','cleanup_collection','cleanup_tables','status'],
                    'example':'{"action":"cleanup_all"}'
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
    logger.info('Cleanup all: Starting complete cleanup process')
    start_time = time.time()
    results = {
        'action':'cleanup_all',
        'timestamp':datetime.utcnow().isoformat(),
        'results':{}
    }

    try:
        logger.info('step 1: Cleaning Rekognition collection...')
        collection_result = cleanup_rekognition_collection_internal()
        results['results']['rekognition_collection'] = collection_result

        logger.info('step 2: cleaning tables dynamodb')
        tables_result = cleanup_dynamodb_tables_internal()
        results['results']['dynamodb_tables'] = tables_result

        total_faces_deleted = collection_result.get('faces_deleted',0)
        total_documents_deleted = tables_result.get('indexed_documents_deleted',0)
        total_comparisons_deleted = tables_result.get('comparison_results_deleted',0)

        processing_time = (time.time()-start_time)*1000

        success = (collection_result.get('success',False) and tables_result.get('success',False))

        results.update({
            'success': success,
            'processing_time_ms':int(processing_time),
            'summary':{
                'faces_deleted': total_faces_deleted,
                'documents_deleted': total_documents_deleted,
                'comparisons_deleted': total_comparisons_deleted,
                'collection_cleaned': collection_result.get('success', False),
                'tables_cleaned': tables_result.get('success', False)
            }
        })

        if success:
            logger.info(f'Cleanup completed: {total_faces_deleted} faces, {total_documents_deleted} documents, {total_comparisons_deleted} comparisons in {processing_time:.0f} ms')
        else:
            logger.warning('Cleanup completed with errors')
        return {
            'statusCode':200,
            'body':json.dumps(results)
        }
    except Exception as e:
        logger.error(f'Error in complete cleanup: {str(e)}')
        results.update({
            'success':False,
            'error':str(e),
            'processing_time_ms': int((time.time()-start_time)*1000)
        })
        return {
            'statusCode':500,
            'body':json.dumps(results)
        }
def cleanup_rekognition_collection():
    logger.info('Cleanup collection: cleaning rekognition collection only')
    result = cleanup_rekognition_collection_internal()

    return {
        'statusCode':200,
        'body': json.dumps({
            'action':'cleanup_collection',
            'timestamp': datetime.utcnow().isoformat(),
            **result
        })
    }

def cleanup_dynamodb_tables():
    logger.info('cleanup tables: cleaning dynamodb tables only')

    result = cleanup_dynamodb_tables_internal()
    return {
        'statusCode':200,
        'body': json.dumps({
            'action':'cleanup_tables',
            'timestamp': datetime.utcnow().isoformat(),
            **result
        })
    }
def cleanup_rekognition_collection_internal():

    start_time = time.time()

    try:
        try:
            collection_info = rekognition_client.describe_collection(CollectionId = COLLECTION_ID)
            initial_face_count = collection_info['FaceCount']
            logger.info(f'Collection {COLLECTION_ID} exists with {initial_face_count} faces')
        except rekognition_client.exceptions.ResourceNotFoundException:
            logger.info(f'Collection {COLLECTION_ID} does not exist')
            return {
                'success': True,
                'faces_deleted':0,
                'message': 'Collection does not exist',
                'processing_time_ms':int((time.time()-start_time)*1000)
            }
        if initial_face_count == 0:
            logger.info('Collection is already empty')
            return {
                'success': True,
                'faces_deleted': 0,
                'message':'Collection already empty',
                'processing_time_ms': int((time.time() - start_time)*1000)
            }
        logger.info('Getting all faces in collection')
        all_face_ids = []

        paginator = rekognition_client.get_paginator('list_faces')
        for page in paginator.paginate(CollectionId = COLLECTION_ID):
            faces = page.get('Faces',[])
            face_ids = [face['FaceId'] for face in faces]
            all_face_ids.extend(face_ids)
        logger.info(f'Found {len(all_face_ids)} faces to delete')

        faces_deleted = 0
        batch_size = 4096

        for i in range(0, len(all_face_ids), batch_size):
            batch = all_face_ids[i:i + batch_size]
            try:
                delete_response = rekognition_client.delete_faces(
                    CollectionId = COLLECTION_ID,
                    FaceIds = batch
                )
                deleted_faces = delete_response.get('DeletedFaces',[])
                faces_deleted += len(deleted_faces)

                logger.info(f'Deleted batch {i//batch_size+1}:{len(deleted_faces)} faces')
            except Exception as e:
                logger.error(f'Error deleting batch {i//batch_size +1}:{str(e)}')
    except Exception as e:
        logger.error(f'Error cleaning Rekognition collection: {str(e)}')
        return {
            'success': False,
            'error': str(e),
            'processing_time_ms': int((time.time()-start_time)*1000)
        }
def cleanup_dynamodb_tables_internal():
    start_time = time.time() 
    try:
        results = {}
        logger.info('Cleaning indexed documents table...')
        indexed_docs_result = cleanup_table(INDEXED_DOCUMENTS_TABLE, 'document_id')
        results['indexed_documents'] = indexed_docs_result

        logger.info('Cleaning comparison results table...')
        comparison_results_result = cleanup_table(COMPARISON_RESULTS_TABLE,'comparison_id','timestamp')
        results['comparison_results'] = comparison_results_result

        total_documents_deleted = indexed_docs_result.get('items_deleted',0)
        total_comparison_deleted = comparison_results_result.get('items_deleted',0)

        all_successful = (indexed_docs_result.get('success',False) and comparison_results_result.get('success',False))
        processing_time = (time.time()-start_time)*1000

        result = {
            'success':all_successful,
            'indexed_documents_deleted':total_documents_deleted,
            'comparison_results_deleted': total_comparison_deleted,
            'tables_cleaned':{
                'indexed_documents':indexed_docs_result.get('success',False),
                'comparison_results':comparison_results_result.get('success',False)
            },
            'details':results,
            'processing_time_ms': int(processing_time)
        }
        logger.info(f'Tables cleanup: {total_documents_deleted} documents, {total_comparison_deleted} comparisons deleted')
        return result
    
    except Exception as e:
        logger.error(f'Error cleaning DynamoDB tables: {str(e)}')
        return {
            'success':False,
            'error':str(e),
            'processing_time_ms': int((time.time()-start_time)*1000)
        }

def cleanup_table(table_name,partition_key,sort_key=None):  
    try:
        table = dynamodb.Table(table_name)
        scan_response = table.scan(Select='COUNT')
        initial_count = scan_response['Count']

        if initial_count == 0:
            logger.info(f'Table {table_name} is already empty')
            return {
                'success':True,
                'items_deleted':0,
                'message':'Table already empty'
            }
        logger.info(f'Table {table_name} has {initial_count} items to delete')

        items_deleted = 0
        scan_kwargs = {
            'ProjectionExpression':partition_key
        }
        if sort_key:
            scan_kwargs['ProjectionExpression'] += f',{sort_key}'
        while True:
            response = table.scan(**scan_kwargs)
            items = response.get('Items',[])
            if not items:
                break
            with table.batch_writer() as batch:
                for item in items:
                    delete_key = {partition_key: item[partition_key]}
                    if sort_key and sort_key in item:
                        delete_key[sort_key] = item[sort_key]
                    
                    batch.delete_item(key=delete_key)
                    items_deleted +=1
            logger.info(f'Deleted batch from {table_name}:{len(items)} items')
            if 'LastEvaluatedKey' not in response:
                break
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        
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









