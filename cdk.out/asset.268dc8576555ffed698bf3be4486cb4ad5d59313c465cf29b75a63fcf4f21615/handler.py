import json
import boto3 
import logging
import os
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)
rekognition = boto3.client('rekognition')

def lambda_handler(event, context):
    logger.info(f'Received event: {json.dumps(event)}')
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin':'*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-type'

    }
    try:
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode' : 200,
                'headers' : headers,
                'body': json.dumps({'message':'CORS preflight'})
            }
        if event.get('httpMethod') == 'POST':
            return create_liveness_session(headers)
        elif event.get('httpMethod') == 'GET':
            return get_liveness_results(event, headers)
        return {
            'statusCode' : 405,
            'headers': headers,
            'body' : json.dumps({'error':'Method not allowed'})
        }
    except Exception as e:
        logger.error(f'Unhandle error: {str(e)}')
        return {
            'statusCode' :500,
            'headers': headers,
            'body': json.dumps({'error':str(e)})
        }
def create_liveness_session(headers):
    try:
        params = {
            'Settings':{
                'AuditImagesLimit': 4,
                'OutputConfig':{
                    'S3Bucket' : os.environ['USER_PHOTOS_BUCKET'],
                    'S3keyPrefix':'liveness-sessions/'
                }
            }
        }
        result = rekognition.create_face_liveness_session(**params)
        logger.info(f'Liveness session created: {result['SessionId']}')
        return {
            'statusCode':200,
            'headers':headers,
            'body': json.dumps({
                'sessionId':result['SessionId'],
                'status' : 'created'
            })
        }
    except Exception as e:
        logger.error(f'Error creating liveness session: {str(e)}')
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error':str(e)})
        }
def get_liveness_results(event, headers):
    try:
        path_parameters = event.get('pathParameters',{})
        session_id = path_parameters.get('sessionId')

        if not session_id:
            return {
                'statusCode':400,
                'headers': headers,
                'body': json.dumps({'error':'sessionId required'})
            }
        results = rekognition.get_face_liveness_session_results(
            SessionId = session_id
        )
        reference_image = results.get('ReferenceImage')
        has_bytes = bool(reference_image and reference_image.get('Bytes'))
        has_s3_object = bool(reference_image and reference_image.get('S3Object'))
        is_available = has_bytes or has_s3_object

        logger.info(f'Liveness results: {results['Status']},confidence: {results.get('Confidence',0)}')
        return {
            'statusCode' : 200,
            'headers':headers,
            'body':json.dumps({
                'status': results['Status'],
                'confidence': float(results.get('Confidence', 0)),
                'referenceImageAvailable': is_available,
                'session_Id': session_id,
                'hasS3Reference': has_s3_object,
                's3Details': reference_image.get('S3Object') if has_s3_object else None
            })
        }
    except Exception as e:
        logger.error(f'Error getting liveness results: {str(e)}')
        return {
            'statusCode':500,
            'headers':headers,
            'body':json.dumps({'error':str(e)})
        }    