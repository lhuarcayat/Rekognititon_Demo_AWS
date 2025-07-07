import json
import boto3
import logging
import os
from decimal import Decimal

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
COMPARISON_RESULTS_TABLE = os.environ['COMPARISON_RESULTS_TABLE']

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(COMPARISON_RESULTS_TABLE)

def lambda_handler(event, context):
    """
    🆕 Check validation results con soporte para errores específicos y reintentos
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    # CORS headers
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    try:
        # Handle preflight OPTIONS request
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'message': 'CORS preflight'})
            }
        
        # Get document number from path parameters
        path_parameters = event.get('pathParameters', {})
        numero_documento = path_parameters.get('numero_documento') if path_parameters else None
        
        if not numero_documento:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'numero_documento path parameter is required'
                })
            }
        
        logger.info(f"Checking validation results for document: {numero_documento}")
        
        # 🆕 Buscar resultados de validación con mejor filtrado
        try:
            response = table.scan(
                FilterExpression='contains(user_image_key, :doc_number)',
                ExpressionAttributeValues={
                    ':doc_number': numero_documento
                }
            )
            
            items = response['Items']
            
            if not items:
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({
                        'match_found': False,
                        'message': 'No validation results found for this document',
                        'found': False
                    })
                }
            
            # 🆕 Obtener el resultado más reciente por timestamp
            latest_result = max(items, key=lambda x: x['timestamp'])
            
            logger.info(f"Found validation result: {latest_result['comparison_id']}")
            
            # Convert Decimal to float for JSON serialization
            result_data = convert_decimals(latest_result)
            
            # 🆕 Determinar si es un match exitoso
            status = result_data.get('status', '')
            confidence = float(result_data.get('confidence_score', 0))
            error_type = result_data.get('error_type')
            allow_retry = result_data.get('allow_retry', True)
            attempt_number = result_data.get('attempt_number', 1)
            
            # 🆕 Clasificación de éxito más granular
            successful_statuses = ['MATCH_CONFIRMED', 'POSSIBLE_MATCH']
            match_found = status in successful_statuses
            
            # 🆕 Base response con campos adicionales
            response_body = {
                'found': True,  # 🆕 Indica que se encontró resultado
                'match_found': match_found,
                'status': status,
                'confidence': confidence,
                'comparison_id': result_data.get('comparison_id'),
                'timestamp': result_data.get('timestamp'),
                'processing_time_ms': result_data.get('processing_time_ms'),
                'user_image_key': result_data.get('user_image_key'),
                
                # 🆕 Campos específicos para manejo de errores y reintentos
                'error_type': error_type,
                'allow_retry': allow_retry,
                'attempt_number': attempt_number,
            }
            
            # Add additional details if match was found
            if match_found:
                response_body.update({
                    'person_name': result_data.get('person_name'),
                    'matched_face_id': result_data.get('matched_face_id'),
                    'search_confidence': float(result_data.get('search_confidence', 0)) if result_data.get('search_confidence') else None,
                    'document_indexed': result_data.get('document_indexed', False)
                })
            
            # 🆕 Add error info if present (for failed attempts)
            if 'error' in result_data:
                response_body['error'] = result_data['error']
            
            # 🆕 Add comparison method if present
            if 'comparison_method' in result_data:
                response_body['comparison_method'] = result_data['comparison_method']
            
            # 🆕 Add document reference
            if 'document_image_key' in result_data:
                response_body['document_image_key'] = result_data['document_image_key']
            
            logger.info(f"Returning result: match_found={match_found}, status={status}, error_type={error_type}, allow_retry={allow_retry}")
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(response_body)
            }
            
        except Exception as db_error:
            logger.error(f"Error querying DynamoDB: {str(db_error)}")
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({
                    'error': f'Failed to query validation results: {str(db_error)}',
                    'found': False,
                    'match_found': False
                })
            }
    
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': f'Internal server error: {str(e)}',
                'found': False,
                'match_found': False
            })
        }

def convert_decimals(obj):
    """
    Convert DynamoDB Decimal objects to float for JSON serialization
    """
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(v) for v in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj