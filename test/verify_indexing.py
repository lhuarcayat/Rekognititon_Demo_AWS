import boto3
import json

# Verificar documentos indexados
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('rekognition-indexed-documents')

def check_indexed_documents():
    """Verificar qué documentos están indexados"""
    try:
        response = table.scan()
        documents = response['Items']
        
        print(f"📊 Total documentos indexados: {len(documents)}")
        print("-" * 50)
        
        for doc in documents:
            print(f"🆔 Document ID: {doc['document_id']}")
            print(f"👤 Persona: {doc['person_name']}")
            print(f"📄 Archivo: {doc['s3_key']}")
            print(f"🎯 Face ID: {doc['face_id']}")
            print(f"📊 Confidence: {doc['confidence_score']}")
            print(f"📅 Indexado: {doc['index_timestamp']}")
            print("-" * 30)
            
        return documents
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

if __name__ == "__main__":
    check_indexed_documents()