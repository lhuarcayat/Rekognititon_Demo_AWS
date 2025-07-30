import json
import boto3
import logging
import os
import sys
import re
sys.path.append('/opt')

# 🆕 Import shared libraries para DetectFaces inmediato
from shared.image_processor import MinimalImageProcessor
from shared.rekognition_client import RekognitionClient

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DOCUMENT_INDEXER_FUNCTION = os.environ['DOCUMENT_INDEXER_FUNCTION']
DOCUMENTS_BUCKET = os.environ['DOCUMENTS_BUCKET']
COLLECTION_ID = os.environ.get('COLLECTION_ID', 'document-faces-collection')

lambda_client = boto3.client('lambda')
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')


# 🆕 Processors para validación inmediata
image_processor = MinimalImageProcessor()
rekognition_client = RekognitionClient(COLLECTION_ID)

def lambda_handler(event, context):
    """
    🆕 API endpoint mejorado para indexar documentos con DetectFaces inmediato
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    # CORS headers
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
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
        
        # Parse request body
        body = json.loads(event['body']) if event.get('body') else {}
        
        s3_key = body.get('s3_key')
        
        if not s3_key:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 's3_key is required',
                    'example': {'s3_key': 'DNI-12345678.jpg'}
                })
            }
        
        # Verificar que el archivo existe en S3
        try:
            s3_client.head_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
            logger.info(f"✅ Document found in S3: {s3_key}")
        except s3_client.exceptions.NoSuchKey:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({
                    'error': f'File {s3_key} not found in bucket {DOCUMENTS_BUCKET}'
                })
            }
        
        # 🆕 STEP 1: IMMEDIATE FACE DETECTION
        logger.info(f'Starting full validation(textract +Face) for {s3_key}')
        validation_result = validate_document_with_textract_and_faces(s3_key)




        #logger.info(f"🔍 Performing immediate face detection on {s3_key}")
        
        #face_validation_result = validate_document_faces(s3_key)
        
        if not validation_result['success']:
            # 🆕 FACE DETECTION FAILED - Delete document and return error
            logger.error(f"❌ Face validation failed for {s3_key}: {validation_result['error']}")
            
            try:
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
                logger.info(f"🗑️  Deleted invalid document: {s3_key}")
            except Exception as delete_error:
                logger.error(f"Failed to delete invalid document {s3_key}: {delete_error}")
            
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': f'Document validation failed: {validation_result["error"]}',
                    'validation_state': validation_result.get('validation_stage','UNKNOWN'),
                    'document_removed': True
                })
            }
        
        # 🆕 STEP 2: Face detection successful - Return success immediately
        # NOTE: Document will be indexed later by user_validator if comparison is successful
        
        logger.info(f"✅ Document validation successful for {s3_key}")
        logger.info(f"📋 Detected faces: {validation_result['face_count']}")
        
        # Extract person name for UI display
        #person_name = extract_person_name(s3_key)
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'message': 'Document validated successfully - number and face confirmed',
                #'person_name': person_name,
                'face_count': validation_result['face_count'],
                'face_confidence': validation_result['face_confidence'],
                'extracted_number':validation_result['extracted_number'],
                'number_confidence':validation_result['number_confidence'],
                'validation_stages':validation_result['validation_stages'],
                'status': 'FULLY_VALIDATED'
            })
        }
                
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
        
        # Try to clean up the uploaded file on any error
        try:
            if 's3_key' in locals():
                s3_client.delete_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
                logger.info(f"Cleaned up failed document: {s3_key}")
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup {s3_key}: {cleanup_error}")
        
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': f'Internal server error: {str(e)}',
                'document_removed': True
            })
        }

def validate_document_with_textract_and_faces(s3_key: str) -> dict:
    """
    🆕 Validar que el documento tiene al menos una cara detectada y textract
    """
    try:
        # STEP 1: Descargar imagen de S3
        expected_number = extract_document_number_from_filename(s3_key)
        if not expected_number:
            return {
                'success':False,
                'error':f'Cannot extract document number from filename: {s3_key}',
                'validation_stage': 'FILENAME_PARSING'
            }
        logger.info(f'Expected number from filename: {expected_number}')
        
        response = s3_client.get_object(Bucket=DOCUMENTS_BUCKET, Key=s3_key)
        image_bytes = response['Body'].read()
        
        logger.info(f"Downloaded {s3_key}: {len(image_bytes)} bytes")
        
        # STEP 2: Procesar imagen
        processed_bytes, error = image_processor.process_image(image_bytes, s3_key)
        if error:
            return {
                'success': False,
                'error': f'Image processing failed: {error}',
                'validation_stage': 'IMAGE_PROCESSING'
            }
        
        # STEP 3: Detectar caras
        logger.info(f'TEXTRACT: starting document number validation')
        textract_result = validate_document_number_with_textract(processed_bytes, expected_number)
        if not textract_result['success']:
            return {
                'success' : False,
                'error'   : f'Document number validation failed: {textract_result["error"]}',
                'validation_stage': 'TEXTRACT_VALIDATION',
                'expected_number': expected_number,
                'extracted_numbers': textract_result.get('extracted_numbers',[])
            }
        logger.info(f'TEXTRACT: Number validated - {textract_result["matched_number"]}')
        logger.info(f'REKOGNITION: starting face detection')

        face_detection = rekognition_client.detect_faces(processed_bytes)
        if not face_detection['success']:
            return {
                'success': False,
                'error': f'Face detection failed: {face_detection["error"]}',
                'validation_stage': 'FACE_DETECTION'
            }
        
        if face_detection['face_count'] == 0:
            return {
                'success': False,
                'error': 'No faces detected in document',
                'validation_stage': 'FACE_DETECTION'
            }
        
        #if face_detection['face_count'] > 1:
        #    logger.warning(f"Multiple faces detected in {s3_key}, but proceeding...")
        
        # STEP 4: Calcular confidence promedio de las caras detectadas
        avg_confidence = 0
        if face_detection.get('faces'):
            confidences = [face.get('Confidence', 0) for face in face_detection['faces']]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        return {
            'success': True,
            'face_count': face_detection['face_count'],
            'face_confidence': avg_confidence,
            'extracted_number': textract_result['matched_number'],
            'number_confidence': textract_result['confidence'],
            'validation_stages': ['FILENAME_PARSING','TEXTRACT_VALIDATION','FACE_DETECTION']
        }
        
    except Exception as e:
        logger.error(f"Error validating faces in {s3_key}: {str(e)}")
        return {
            'success': False,
            'error': f'Face validation error: {str(e)}',
            'validation_stage': 'SYSTEM_ERROR'
        }

def extract_document_number_from_filename(s3_key: str) -> str:
    try:
        filename = os.path.basename(s3_key)
        base_name = os.path.splitext(filename)[0]
        parts = base_name.split('-')
        if len(parts) >= 2:
            return parts [1]
        return None
    
    except Exception as e:
        logger.error(f'Error extracting number from filename {s3_key}: {str(e)}')
        return None

def validate_document_number_with_textract(image_bytes: bytes, expected_number: str) -> dict:
    try:
        queries_sequence = [
            {
                'Text': 'what is the document number',
                'Alias': 'DOCUMENT_NUMBER_PRIMARY'
            },
            {
                'Text': 'what is the number in NUMERO',
                'Alias': 'NUMERO_FALLBACK'
            },
            {
                'Text': 'what is the number in NUIP',
                'Alias': 'NUIP_FALLBACK'
            }
        ]

        logger.info(f'Expected number: {expected_number}')

        for i, query in enumerate(queries_sequence):
            logger.info(f"Trying query {i+1}: '{query['Text']}'")

            try:
                response = textract_client.analyze_document(
                    Document = {'Bytes': image_bytes},
                    FeatureTypes = ['QUERIES'],
                    QueriesConfig = {'Queries':[query]}
                )

                extracted_numbers = []

                for block in response['Blocks']:
                    if block['BlockType'] == 'QUERY_RESULT':
                        if block.get('Query',{}).get('Alias') == query['Alias']:
                            if block.get('Text') and block['Text'].strip():
                                extracted_numbers.append({
                                    'text':block['Text'].strip(),
                                    'confidence': block.get('Confidence',0)
                                })
                
                logger.info(f'Query {i+1} extracted: {extracted_numbers}')

                valid_extractions = [
                    e for e in extracted_numbers
                    if e['confidence'] >= 80.0
                ]

                if not valid_extractions:
                    logger.info(f'Query {i+1}: No valid extractions (confidence < 80%)')
                    continue
                if i==0 and len(valid_extractions) > 1:
                    cleaned_numbers = [clean_document_number(e['Text']) for e in valid_extractions]
                    unique_numbers = list(set(cleaned_numbers))

                    if len(unique_numbers) > 1:
                        logger.error(f'Primary query returned multiple DIFFERENT numbers: {unique_numbers}')
                        return {
                            'success' : False,
                            'error'   : f'Multiple different numbers found in document: {[e["text"] for e in valid_extractions]}',
                            'extracted_numbers': valid_extractions
                        }
                
                for extraction in valid_extractions:
                    extracted_text = extraction['text']

                    cleaned_extracted = clean_document_number(extracted_text)
                    cleaned_expected = clean_document_number(expected_number)

                    logger.info(f'Comparing: {cleaned_extracted} vs {cleaned_expected}')

                    if cleaned_extracted in cleaned_expected:
                        logger.info(f'Match found with query {i+1}')
                        return {
                            'success':True,
                            'matched_number': extracted_text,
                            'expected_number': expected_number,
                            'confidence': extraction['confidence'],
                            'query_used': query['Text']
                        }
                    logger.info(f'Query {i+1}: No match found, trying next query')
            except Exception as query_error:
                logger.error(f'Error in query {i+1}: {str(query_error)}')
                continue
        return {
            'success': False,
            'error': f'No matching document number found. Expected {expected_number}',
            'expected_number': expected_number
        }
    except Exception as e:
        logger.error(f'Textract validation error: {str(e)}')
        return {
            'success' : False,
            'error'   : f'Textract analysis failed: {str(e)}'
        }
def clean_document_number(number_str:str) -> str:
    if not number_str:
        return ''
    cleaned = number_str.strip()
    cleaned = cleaned.replace('.','')
    cleaned = re.sub(r'[^\d]', '', cleaned)
    return cleaned


#def extract_person_name(s3_key: str) -> str:
#    """
#    Extraer nombre de persona desde el nombre del archivo
#    """
#    try:
#        base_name = os.path.splitext(os.path.basename(s3_key))[0]
#        name = base_name.replace('_', ' ').replace('-', ' ')
#        remove_words = ['dni', 'cedula', 'passport', 'documento', 'doc', 'id']
#        words = [word for word in name.split() if word.lower() not in remove_words]
#        return ' '.join(word.capitalize() for word in words) if words else base_name
#    except Exception as e:
#        logger.error(f"Error extracting person name from {s3_key}: {str(e)}")
#        return "Unknown"