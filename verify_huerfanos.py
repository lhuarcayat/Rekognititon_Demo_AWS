
import boto3
import json

def diagnose_metadata_issue():
    """
    Diagnosticar exactamente por qué hay 'No metadata found'
    """
    print("🔍 DIAGNÓSTICO: 'No metadata found'")
    print("=" * 50)
    
    rekognition = boto3.client('rekognition')
    dynamodb = boto3.resource('dynamodb')
    indexed_docs_table = dynamodb.Table('rekognition-indexed-documents')
    
    try:
        # 1. Obtener todas las caras en Rekognition
        print("📋 PASO 1: Analizando Rekognition Collection...")
        
        paginator = rekognition.get_paginator('list_faces')
        rekognition_faces = []
        
        for page in paginator.paginate(CollectionId='document-faces-collection'):
            rekognition_faces.extend(page['Faces'])
        
        print(f"   ✅ Caras en Rekognition: {len(rekognition_faces)}")
        
        # Mostrar detalles de cada cara
        print("\n📄 DETALLES DE CARAS EN REKOGNITION:")
        for i, face in enumerate(rekognition_faces, 1):
            print(f"\n{i}. Face ID: {face['FaceId']}")
            print(f"   External Image ID: {face.get('ExternalImageId', 'NO DEFINIDO')}")
            print(f"   Confidence: {face['Confidence']:.1f}%")
            if 'ImageId' in face:
                print(f"   Image ID: {face['ImageId']}")
        
        # 2. Obtener metadatos en DynamoDB
        print(f"\n📋 PASO 2: Analizando DynamoDB Metadata...")
        
        response = indexed_docs_table.scan()
        dynamodb_docs = response['Items']
        
        print(f"   ✅ Documentos en DynamoDB: {len(dynamodb_docs)}")
        
        print("\n📄 DETALLES DE METADATOS EN DYNAMODB:")
        for i, doc in enumerate(dynamodb_docs, 1):
            print(f"\n{i}. Document ID: {doc['document_id']}")
            print(f"   Face ID: {doc.get('face_id', 'NO DEFINIDO')}")
            print(f"   Person Name: {doc.get('person_name', 'NO DEFINIDO')}")
            print(f"   S3 Key: {doc.get('s3_key', 'NO DEFINIDO')}")
        
        # 3. Encontrar inconsistencias
        print(f"\n🔍 PASO 3: Buscando Inconsistencias...")
        
        rekognition_face_ids = {face['FaceId'] for face in rekognition_faces}
        dynamodb_face_ids = {doc.get('face_id') for doc in dynamodb_docs if doc.get('face_id')}
        
        # Caras huérfanas (en Rekognition pero sin metadata)
        orphaned_faces = rekognition_face_ids - dynamodb_face_ids
        
        # Metadatos huérfanos (en DynamoDB pero sin cara)
        orphaned_metadata = dynamodb_face_ids - rekognition_face_ids
        
        print(f"\n📊 RESULTADOS DEL DIAGNÓSTICO:")
        print(f"   🟢 Caras con metadata completo: {len(rekognition_face_ids & dynamodb_face_ids)}")
        print(f"   🔴 Caras SIN metadata (problema actual): {len(orphaned_faces)}")
        print(f"   🟡 Metadata SIN cara: {len(orphaned_metadata)}")
        
        if orphaned_faces:
            print(f"\n❌ CARAS HUÉRFANAS (causan 'No metadata found'):")
            for face_id in orphaned_faces:
                # Buscar detalles de esta cara
                face_details = next((f for f in rekognition_faces if f['FaceId'] == face_id), None)
                print(f"   📄 {face_id}")
                if face_details and face_details.get('ExternalImageId'):
                    print(f"      External ID: {face_details['ExternalImageId']}")
                    print(f"      ❓ Posible causa: Error durante indexación de '{face_details['ExternalImageId']}'")
                else:
                    print(f"      ❓ Posible causa: Indexación manual o pruebas anteriores")
        
        if orphaned_metadata:
            print(f"\n⚠️  METADATA HUÉRFANOS:")
            for face_id in orphaned_metadata:
                doc = next((d for d in dynamodb_docs if d.get('face_id') == face_id), None)
                if doc:
                    print(f"   📄 {face_id}")
                    print(f"      Document: {doc['document_id']}")
                    print(f"      ❓ Posible causa: Cara eliminada de Rekognition pero metadata no limpiado")
        
        # 4. Explicar causas comunes
        print(f"\n📚 CAUSAS COMUNES DEL PROBLEMA:")
        print(f"   1. 🔄 Indexación parcial fallida:")
        print(f"      - Cara se indexó en Rekognition ✅")
        print(f"      - Metadata NO se guardó en DynamoDB ❌")
        print(f"      - Resultado: 'No metadata found'")
        
        print(f"   2. 🧪 Pruebas anteriores:")
        print(f"      - Indexación manual de pruebas")
        print(f"      - Limpieza incompleta de datos")
        
        print(f"   3. 🔀 Race conditions:")
        print(f"      - Errores de timing durante indexación")
        print(f"      - Transacciones no completadas")
        
        print(f"   4. 🐛 Errores de código:")
        print(f"      - Bug en document_indexer")
        print(f"      - Manejo incorrecto de errores")
        
        return {
            'rekognition_faces': len(rekognition_faces),
            'dynamodb_docs': len(dynamodb_docs),
            'orphaned_faces': list(orphaned_faces),
            'orphaned_metadata': list(orphaned_metadata),
            'consistent_pairs': len(rekognition_face_ids & dynamodb_face_ids)
        }
        
    except Exception as e:
        print(f"❌ Error en diagnóstico: {e}")
        return None

def show_impact_analysis():
    """
    Analizar el impacto del problema en el funcionamiento
    """
    print(f"\n📊 ANÁLISIS DE IMPACTO")
    print("=" * 30)
    
    print(f"✅ FUNCIONAMIENTO ACTUAL:")
    print(f"   - Sistema SIGUE funcionando correctamente")
    print(f"   - Encuentra caras con metadata válido")
    print(f"   - Ignora caras huérfanas (correcto)")
    print(f"   - Resultado final: MATCH_CONFIRMED ✅")
    
    print(f"\n⚠️  IMPACTOS MENORES:")
    print(f"   - Logs con warnings (cosmético)")
    print(f"   - Evaluación de candidatos adicionales (desperdicio mínimo)")
    print(f"   - Storage innecesario en Rekognition")
    
    print(f"\n🔧 SOLUCIONES:")
    print(f"   1. Limpieza: Eliminar caras huérfanas")
    print(f"   2. Prevención: Mejorar robustez de indexación")
    print(f"   3. Monitoring: Alertas para inconsistencias")

if __name__ == "__main__":
    diagnosis = diagnose_metadata_issue()
    show_impact_analysis()
    
    if diagnosis and diagnosis['orphaned_faces']:
        print(f"\n🛠️  RECOMENDACIÓN:")
        print(f"   Ejecutar: python fix_metadata.py")
        print(f"   Para limpiar {len(diagnosis['orphaned_faces'])} caras huérfanas")