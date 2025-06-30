import boto3
import json
from datetime import datetime

def detect_orphaned_faces():
    """
    Detectar automáticamente todas las caras huérfanas
    """
    print("🔍 DETECTANDO CARAS HUÉRFANAS AUTOMÁTICAMENTE...")
    print("=" * 60)
    
    try:
        rekognition = boto3.client('rekognition')
        dynamodb = boto3.resource('dynamodb')
        indexed_docs_table = dynamodb.Table('rekognition-indexed-documents')
        
        # 1. Obtener todas las caras en Rekognition
        print("📋 Obteniendo caras de Rekognition Collection...")
        paginator = rekognition.get_paginator('list_faces')
        rekognition_faces = []
        
        for page in paginator.paginate(CollectionId='document-faces-collection'):
            rekognition_faces.extend(page['Faces'])
        
        print(f"   ✅ Caras en Rekognition: {len(rekognition_faces)}")
        
        # 2. Obtener metadatos en DynamoDB
        print("📋 Obteniendo metadatos de DynamoDB...")
        response = indexed_docs_table.scan()
        dynamodb_docs = response['Items']
        
        print(f"   ✅ Documentos en DynamoDB: {len(dynamodb_docs)}")
        
        # 3. Encontrar inconsistencias
        print("🔍 Analizando inconsistencias...")
        
        rekognition_face_ids = {face['FaceId'] for face in rekognition_faces}
        dynamodb_face_ids = {doc.get('face_id') for doc in dynamodb_docs if doc.get('face_id')}
        
        # Caras huérfanas (en Rekognition pero sin metadata)
        orphaned_faces = rekognition_face_ids - dynamodb_face_ids
        
        # Metadatos huérfanos (en DynamoDB pero sin cara)
        orphaned_metadata = dynamodb_face_ids - rekognition_face_ids
        
        print(f"\n📊 ANÁLISIS DE INCONSISTENCIAS:")
        print(f"   🟢 Caras con metadata completo: {len(rekognition_face_ids & dynamodb_face_ids)}")
        print(f"   🔴 Caras SIN metadata (huérfanas): {len(orphaned_faces)}")
        print(f"   🟡 Metadata SIN cara: {len(orphaned_metadata)}")
        
        # Mostrar detalles de caras huérfanas
        if orphaned_faces:
            print(f"\n❌ CARAS HUÉRFANAS DETECTADAS:")
            for i, face_id in enumerate(sorted(orphaned_faces), 1):
                # Buscar detalles de esta cara
                face_details = next((f for f in rekognition_faces if f['FaceId'] == face_id), None)
                print(f"   {i}. {face_id}")
                if face_details:
                    external_id = face_details.get('ExternalImageId', 'NO DEFINIDO')
                    confidence = face_details.get('Confidence', 0)
                    print(f"      External ID: {external_id}")
                    print(f"      Confidence: {confidence:.1f}%")
        
        return {
            'orphaned_faces': list(orphaned_faces),
            'orphaned_metadata': list(orphaned_metadata),
            'consistent_pairs': len(rekognition_face_ids & dynamodb_face_ids),
            'rekognition_faces_details': {face['FaceId']: face for face in rekognition_faces}
        }
        
    except Exception as e:
        print(f"❌ Error detectando huérfanos: {e}")
        return None

def clean_orphaned_faces():
    """
    Limpiar automáticamente todas las caras huérfanas detectadas
    """
    print("🧹 LIMPIEZA AUTOMÁTICA DE CARAS HUÉRFANAS")
    print("=" * 60)
    
    # Detectar caras huérfanas automáticamente
    detection_result = detect_orphaned_faces()
    
    if not detection_result:
        print("❌ No se pudo detectar caras huérfanas")
        return False
    
    orphaned_faces = detection_result['orphaned_faces']
    face_details = detection_result['rekognition_faces_details']
    
    if not orphaned_faces:
        print("🎉 ¡NO SE ENCONTRARON CARAS HUÉRFANAS!")
        print("   El sistema está limpio y consistente")
        return True
    
    print(f"\n🎯 Caras huérfanas a eliminar: {len(orphaned_faces)}")
    
    # Mostrar lista detallada
    print(f"\n📋 LISTA DE CARAS A ELIMINAR:")
    for i, face_id in enumerate(sorted(orphaned_faces), 1):
        face_info = face_details.get(face_id, {})
        external_id = face_info.get('ExternalImageId', 'NO DEFINIDO')
        confidence = face_info.get('Confidence', 0)
        
        print(f"   {i}. {face_id}")
        print(f"      External ID: {external_id}")
        print(f"      Confidence: {confidence:.1f}%")
    
    # Explicación y confirmación
    print(f"\n⚠️  IMPORTANTE:")
    print(f"   - Estas son caras indexadas en Rekognition SIN metadatos en DynamoDB")
    print(f"   - Eliminarlas resolverá los warnings 'No metadata found'")
    print(f"   - Las caras válidas con metadata se mantendrán intactas")
    print(f"   - Esta operación es IRREVERSIBLE")
    
    print(f"\n🔍 VERIFICACIÓN:")
    print(f"   - Caras válidas: {detection_result['consistent_pairs']}")
    print(f"   - Caras huérfanas: {len(orphaned_faces)}")
    print(f"   - Metadatos huérfanos: {len(detection_result['orphaned_metadata'])}")
    
    # Confirmación del usuario
    print(f"\n" + "="*50)
    confirm = input(f"¿Proceder con la eliminación de {len(orphaned_faces)} caras huérfanas? (y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Operación cancelada por el usuario")
        return False
    
    # Proceder con la eliminación
    try:
        rekognition = boto3.client('rekognition')
        collection_id = 'document-faces-collection'
        
        print(f"\n🗑️  Eliminando {len(orphaned_faces)} caras huérfanas...")
        
        deleted_count = 0
        errors = []
        
        # Eliminar en lotes para mejor performance
        batch_size = 10  # Rekognition permite hasta 100, pero 10 es más seguro
        
        for i in range(0, len(orphaned_faces), batch_size):
            batch = orphaned_faces[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(orphaned_faces) + batch_size - 1) // batch_size
            
            print(f"\n   📦 Lote {batch_num}/{total_batches} ({len(batch)} caras):")
            
            try:
                response = rekognition.delete_faces(
                    CollectionId=collection_id,
                    FaceIds=batch
                )
                
                deleted_in_batch = len(response.get('DeletedFaces', []))
                deleted_count += deleted_in_batch
                
                # Mostrar resultados del lote
                for j, face_id in enumerate(batch, 1):
                    if face_id in response.get('DeletedFaces', []):
                        print(f"      {j}. ✅ {face_id}")
                    else:
                        print(f"      {j}. ⚠️  {face_id} (no eliminada)")
                        errors.append(f"{face_id}: No encontrada en colección")
                
                # Procesar errores del lote si los hay
                for error in response.get('UnsuccessfulFacesDeletions', []):
                    face_id = error.get('FaceId', 'unknown')
                    reason = error.get('Reason', 'unknown')
                    errors.append(f"{face_id}: {reason}")
                    print(f"      ❌ Error eliminando {face_id}: {reason}")
                    
            except Exception as e:
                print(f"      ❌ Error en lote {batch_num}: {str(e)}")
                for face_id in batch:
                    errors.append(f"{face_id}: Error en lote - {str(e)}")
        
        # Reporte final de eliminación
        print(f"\n📊 RESULTADO DE LIMPIEZA:")
        print(f"   ✅ Caras eliminadas exitosamente: {deleted_count}/{len(orphaned_faces)}")
        print(f"   ❌ Errores: {len(errors)}")
        
        if errors:
            print(f"\n⚠️  ERRORES ENCONTRADOS:")
            for error in errors[:10]:  # Mostrar solo primeros 10 errores
                print(f"   - {error}")
            if len(errors) > 10:
                print(f"   ... y {len(errors) - 10} errores más")
        
        success_rate = (deleted_count / len(orphaned_faces)) * 100 if orphaned_faces else 100
        
        if success_rate >= 95:
            print(f"\n🎉 ¡LIMPIEZA COMPLETADA EXITOSAMENTE!")
            print(f"   - Tasa de éxito: {success_rate:.1f}%")
            print(f"   - Los warnings 'No metadata found' deberían desaparecer")
            print(f"   - Las caras válidas permanecen intactas")
        else:
            print(f"\n⚠️  LIMPIEZA PARCIALMENTE EXITOSA")
            print(f"   - Tasa de éxito: {success_rate:.1f}%")
            print(f"   - Revisar errores arriba")
        
        return success_rate >= 95
        
    except Exception as e:
        print(f"\n❌ Error durante limpieza: {e}")
        return False

def verify_cleanup():
    """
    Verificar que la limpieza fue exitosa
    """
    print(f"\n🔍 VERIFICANDO RESULTADOS DE LA LIMPIEZA...")
    print("=" * 50)
    
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
        
        print(f"📊 ESTADO POST-LIMPIEZA:")
        print(f"   ✅ Caras en Rekognition: {len(remaining_faces)}")
        print(f"   ✅ Metadatos en DynamoDB: {len(metadata_records)}")
        
        # Verificar consistencia
        rekognition_face_ids = {face['FaceId'] for face in remaining_faces}
        metadata_face_ids = {record['face_id'] for record in metadata_records}
        
        # Encontrar nuevas inconsistencias
        orphaned_faces = rekognition_face_ids - metadata_face_ids
        orphaned_metadata = metadata_face_ids - rekognition_face_ids
        consistent_pairs = len(rekognition_face_ids & metadata_face_ids)
        
        print(f"\n📈 ANÁLISIS DE CONSISTENCIA:")
        print(f"   🟢 Pares consistentes: {consistent_pairs}")
        print(f"   🔴 Caras sin metadata: {len(orphaned_faces)}")
        print(f"   🟡 Metadata sin cara: {len(orphaned_metadata)}")
        
        if not orphaned_faces and not orphaned_metadata:
            print(f"\n🎯 ¡PERFECTO! Sistema completamente consistente")
            print(f"   ✅ Todas las caras tienen metadata")
            print(f"   ✅ Todos los metadatos tienen cara")
            print(f"   🚫 No más warnings 'No metadata found'")
            return True
        else:
            if orphaned_faces:
                print(f"\n⚠️  Aún hay {len(orphaned_faces)} caras sin metadata:")
                for face_id in list(orphaned_faces)[:5]:
                    print(f"      - {face_id}")
                if len(orphaned_faces) > 5:
                    print(f"      ... y {len(orphaned_faces) - 5} más")
            
            if orphaned_metadata:
                print(f"\n⚠️  Hay {len(orphaned_metadata)} metadatos sin cara:")
                for face_id in list(orphaned_metadata)[:5]:
                    print(f"      - {face_id}")
                if len(orphaned_metadata) > 5:
                    print(f"      ... y {len(orphaned_metadata) - 5} más")
            
            return False
            
    except Exception as e:
        print(f"   ❌ Error verificando: {e}")
        return False

def show_final_state():
    """
    Mostrar estado final del sistema después de limpieza
    """
    print(f"\n📋 ESTADO FINAL DEL SISTEMA")
    print("=" * 50)
    
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
        
        print(f"👥 RESUMEN DEL SISTEMA:")
        print(f"   📊 Total caras indexadas: {len(faces)}")
        print(f"   📊 Total documentos: {len(metadata)}")
        
        # Agrupar por persona
        people = {}
        for record in metadata:
            person_name = record['person_name']
            if person_name not in people:
                people[person_name] = []
            people[person_name].append(record)
        
        print(f"   👥 Personas únicas: {len(people)}")
        
        print(f"\n👤 PERSONAS EN EL SISTEMA:")
        for person, records in people.items():
            print(f"\n   📋 {person}:")
            for record in records:
                face_id = record['face_id']
                doc_type = record.get('document_type', 'DOCUMENT')
                s3_key = record['s3_key']
                
                # Verificar que la cara existe en Rekognition
                face_exists = any(f['FaceId'] == face_id for f in faces)
                status = "✅ Activa" if face_exists else "❌ Faltante"
                
                print(f"      📄 {doc_type}: {status}")
                print(f"         🆔 Face ID: {face_id[:8]}...")
                print(f"         📁 Archivo: {s3_key}")
        
        # Verificar integridad final
        if len(faces) == len(metadata):
            print(f"\n🎯 INTEGRIDAD: ✅ PERFECTA (1:1 correspondencia)")
        else:
            print(f"\n⚠️  INTEGRIDAD: Revisar inconsistencias")
            print(f"   Diferencia: {abs(len(faces) - len(metadata))}")
            
    except Exception as e:
        print(f"❌ Error mostrando estado final: {e}")

def main():
    """
    Proceso completo de detección y limpieza automática
    """
    print("🚀 LIMPIEZA AUTOMÁTICA DE CARAS HUÉRFANAS")
    print("=" * 70)
    print(f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🎯 Objetivo: Eliminar automáticamente todas las caras sin metadata")
    
    try:
        # 1. Detectar y limpiar caras huérfanas
        cleanup_success = clean_orphaned_faces()
        
        if not cleanup_success:
            print("\n❌ Limpieza no se completó exitosamente")
            print("🔧 Revisar errores arriba para más detalles")
            return False
        
        # 2. Verificar resultados
        verification_success = verify_cleanup()
        
        # 3. Mostrar estado final
        show_final_state()
        
        # 4. Recomendaciones finales
        print(f"\n🎯 PRÓXIMOS PASOS:")
        if verification_success:
            print(f"   ✅ Sistema limpio y consistente")
            print(f"   🧪 Probar validación de usuario para confirmar")
            print(f"   📊 Monitorear logs (sin warnings)")
            print(f"   🔄 Considerar ejecutar verify_success.py")
        else:
            print(f"   ⚠️  Revisar inconsistencias restantes")
            print(f"   🔄 Considerar re-ejecutar el script")
            print(f"   🛠️  Investigar causas de inconsistencias")
        
        print(f"\n💡 PARA PROBAR EL SISTEMA:")
        print(f"   1. Subir nueva foto a S3: aws s3 cp foto.jpg s3://user-photos-bucket/")
        print(f"   2. Verificar logs de validación (sin warnings)")
        print(f"   3. Ejecutar: python verify_success.py")
        print(f"   4. Monitorear: python scripts/test_monitor.py trends")
        
        return verification_success
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Operación interrumpida por el usuario")
        return False
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)