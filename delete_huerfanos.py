import boto3
import json
from datetime import datetime

def clean_orphaned_faces():
    """
    Limpiar específicamente las caras huérfanas identificadas
    """
    print("🧹 LIMPIEZA DE CARAS HUÉRFANAS")
    print("=" * 50)
    
    # Las 3 caras huérfanas identificadas en el diagnóstico
    orphaned_faces = [
        #"50ddc5c2-f962-4c23-b1a5-ad123f534ab8",  # Luis Licencia (014519)
        #"824e4eb0-b64a-42c7-9d7d-73c3af7c99a9",  # Luis DNI (014518)
        #"7e420c0a-a207-4851-a6ff-0cb3590d0728"   # Laura Carne (014517)
    ]
    
    print(f"🎯 Caras a eliminar: {len(orphaned_faces)}")
    for i, face_id in enumerate(orphaned_faces, 1):
        print(f"   {i}. {face_id}")
    
    # Confirmar eliminación
    print(f"\n⚠️  IMPORTANTE:")
    print(f"   - Estas son caras DUPLICADAS de la primera indexación fallida")
    print(f"   - Las caras válidas con metadata se mantendrán intactas")
    print(f"   - Esto eliminará los warnings 'No metadata found'")
    
    confirm = input(f"\n¿Proceder con la limpieza? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Operación cancelada")
        return False
    
    try:
        rekognition = boto3.client('rekognition')
        collection_id = 'document-faces-collection'
        
        print(f"\n🗑️  Eliminando caras huérfanas...")
        
        deleted_count = 0
        errors = []
        
        for i, face_id in enumerate(orphaned_faces, 1):
            try:
                print(f"   {i}/3 Eliminando {face_id}...", end="")
                
                response = rekognition.delete_faces(
                    CollectionId=collection_id,
                    FaceIds=[face_id]
                )
                
                if response['DeletedFaces']:
                    print(" ✅")
                    deleted_count += 1
                else:
                    print(" ⚠️  No encontrada")
                    errors.append(f"{face_id}: No encontrada en colección")
                    
            except Exception as e:
                print(f" ❌ Error: {str(e)}")
                errors.append(f"{face_id}: {str(e)}")
        
        # Verificar resultado
        print(f"\n📊 RESULTADO DE LIMPIEZA:")
        print(f"   ✅ Caras eliminadas: {deleted_count}/3")
        print(f"   ❌ Errores: {len(errors)}")
        
        if errors:
            print(f"\n⚠️  ERRORES ENCONTRADOS:")
            for error in errors:
                print(f"   - {error}")
        
        if deleted_count == 3:
            print(f"\n🎉 ¡LIMPIEZA COMPLETADA EXITOSAMENTE!")
            print(f"   - Se eliminaron todas las caras huérfanas")
            print(f"   - Los warnings 'No metadata found' deberían desaparecer")
            print(f"   - Las caras válidas permanecen intactas")
        
        return deleted_count == 3
        
    except Exception as e:
        print(f"\n❌ Error durante limpieza: {e}")
        return False

def verify_cleanup():
    """
    Verificar que la limpieza fue exitosa
    """
    print(f"\n🔍 VERIFICANDO LIMPIEZA...")
    
    try:
        rekognition = boto3.client('rekognition')
        dynamodb = boto3.resource('dynamodb')
        
        # Obtener caras restantes en Rekognition
        paginator = rekognition.get_paginator('list_faces')
        remaining_faces = []
        
        for page in paginator.paginate(CollectionId='document-faces-collection'):
            remaining_faces.extend(page['Faces'])
        
        # Obtener metadatos en DynamoDB
        table = dynamodb.Table('rekognition-indexed-documents')
        response = table.scan()
        metadata_records = response['Items']
        
        print(f"   ✅ Caras en Rekognition: {len(remaining_faces)}")
        print(f"   ✅ Metadatos en DynamoDB: {len(metadata_records)}")
        
        # Verificar consistencia
        rekognition_face_ids = {face['FaceId'] for face in remaining_faces}
        metadata_face_ids = {record['face_id'] for record in metadata_records}
        
        orphaned_faces = rekognition_face_ids - metadata_face_ids
        
        if not orphaned_faces:
            print(f"   🎯 ¡PERFECTO! Todas las caras tienen metadata")
            print(f"   🚫 No más 'No metadata found'")
            return True
        else:
            print(f"   ⚠️  Aún hay {len(orphaned_faces)} caras sin metadata:")
            for face_id in orphaned_faces:
                print(f"      - {face_id}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error verificando: {e}")
        return False

def show_final_state():
    """
    Mostrar estado final del sistema después de limpieza
    """
    print(f"\n📋 ESTADO FINAL DEL SISTEMA")
    print("=" * 40)
    
    try:
        rekognition = boto3.client('rekognition')
        dynamodb = boto3.resource('dynamodb')
        
        # Caras en Rekognition
        paginator = rekognition.get_paginator('list_faces')
        faces = []
        for page in paginator.paginate(CollectionId='document-faces-collection'):
            faces.extend(page['Faces'])
        
        # Metadatos en DynamoDB
        table = dynamodb.Table('rekognition-indexed-documents')
        response = table.scan()
        metadata = response['Items']
        
        print(f"👥 PERSONAS EN EL SISTEMA:")
        
        # Agrupar por persona
        people = {}
        for record in metadata:
            person_name = record['person_name']
            if person_name not in people:
                people[person_name] = []
            people[person_name].append(record)
        
        for person, records in people.items():
            print(f"\n👤 {person}:")
            for record in records:
                face_id = record['face_id']
                doc_type = record.get('document_type', 'DOCUMENT')
                s3_key = record['s3_key']
                
                # Verificar que la cara existe en Rekognition
                face_exists = any(f['FaceId'] == face_id for f in faces)
                status = "✅ Activa" if face_exists else "❌ Faltante"
                
                print(f"   📄 {doc_type}: {status}")
                print(f"      🆔 Face ID: {face_id[:8]}...")
                print(f"      📁 Archivo: {s3_key}")
        
        print(f"\n📊 RESUMEN:")
        print(f"   Personas únicas: {len(people)}")
        print(f"   Documentos totales: {len(metadata)}")
        print(f"   Caras indexadas: {len(faces)}")
        
        # Verificar integridad
        if len(faces) == len(metadata):
            print(f"   🎯 Integridad: ✅ PERFECTA (1:1)")
        else:
            print(f"   ⚠️  Integridad: Revisar inconsistencias")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """
    Proceso completo de limpieza
    """
    print("🚀 PROCESO DE LIMPIEZA DE DUPLICADOS")
    print("=" * 60)
    
    # 1. Limpiar caras huérfanas
    cleanup_success = clean_orphaned_faces()
    
    if not cleanup_success:
        print("\n❌ Limpieza falló. Revisar errores arriba.")
        return
    
    # 2. Verificar limpieza
    verification_success = verify_cleanup()
    
    # 3. Mostrar estado final
    show_final_state()
    
    # 4. Recomendaciones finales
    print(f"\n🎯 PRÓXIMOS PASOS:")
    if verification_success:
        print(f"   ✅ Sistema limpio y consistente")
        print(f"   🧪 Probar nueva validación para confirmar")
        print(f"   📊 No más warnings 'No metadata found'")
    else:
        print(f"   ⚠️  Revisar inconsistencias restantes")
        print(f"   🔄 Considerar re-indexación completa")
    
    print(f"\n💡 Para probar:")
    print(f"   1. Subir nueva foto a S3")
    print(f"   2. Verificar logs (sin warnings)")
    print(f"   3. python verify_success.py")

if __name__ == "__main__":
    main()