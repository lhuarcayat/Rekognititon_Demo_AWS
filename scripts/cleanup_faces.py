#!/usr/bin/env python3
"""
Script para limpiar rostros de la colección Rekognition
"""

import boto3
import json
import sys


def cleanup_rekognition_collection(collection_id='document-faces-collection'):
    """
    Eliminar todos los rostros de una colección Rekognition
    """
    
    rekognition = boto3.client('rekognition')
    
    try:
        # 1. Listar todos los rostros
        print(f"🔍 Obteniendo rostros de la colección: {collection_id}")
        
        response = rekognition.list_faces(CollectionId=collection_id)
        faces = response['Faces']
        
        if not faces:
            print("✅ La colección ya está vacía")
            return
        
        print(f"📊 Encontrados {len(faces)} rostros en la colección")
        
        # Mostrar rostros encontrados
        for i, face in enumerate(faces, 1):
            external_id = face.get('ExternalImageId', 'N/A')
            face_id = face['FaceId']
            confidence = face.get('Confidence', 0)
            print(f"   {i}. {external_id} (FaceId: {face_id[:8]}..., Confidence: {confidence:.1f}%)")
        
        # Confirmar eliminación
        print(f"\n⚠️  ¿Estás seguro de que quieres eliminar TODOS los {len(faces)} rostros?")
        confirm = input("Escribe 'CONFIRMAR' para continuar: ")
        
        if confirm != 'CONFIRMAR':
            print("❌ Operación cancelada")
            return
        
        # 2. Eliminar rostros en lotes de 4096 (límite de AWS)
        face_ids = [face['FaceId'] for face in faces]
        batch_size = 4096
        
        for i in range(0, len(face_ids), batch_size):
            batch = face_ids[i:i + batch_size]
            
            print(f"🗑️  Eliminando lote {i//batch_size + 1} ({len(batch)} rostros)...")
            
            delete_response = rekognition.delete_faces(
                CollectionId=collection_id,
                FaceIds=batch
            )
            
            deleted_count = len(delete_response['DeletedFaces'])
            print(f"   ✅ Eliminados: {deleted_count}")
            
            if delete_response.get('UnsuccessfulFaceDeletions'):
                print(f"   ⚠️  No eliminados: {len(delete_response['UnsuccessfulFaceDeletions'])}")
        
        print(f"\n🎉 ¡Limpieza completada! Colección {collection_id} está ahora vacía")
        
    except rekognition.exceptions.ResourceNotFoundException:
        print(f"❌ Error: La colección '{collection_id}' no existe")
    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")

def cleanup_dynamodb_records():
    """
    Opcional: También limpiar registros de DynamoDB
    """
    
    print("\n🔍 ¿También quieres limpiar los registros de DynamoDB?")
    cleanup_db = input("Escribe 'SI' para limpiar la tabla indexed-documents: ")
    
    if cleanup_db == 'SI':
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('rekognition-indexed-documents')
        
        try:
            # Scan y eliminar todos los items
            response = table.scan()
            items = response['Items']
            
            if not items:
                print("✅ La tabla DynamoDB ya está vacía")
                return
            
            print(f"📊 Encontrados {len(items)} registros en DynamoDB")
            
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={'document_id': item['document_id']})
            
            print(f"✅ Eliminados {len(items)} registros de DynamoDB")
            
        except Exception as e:
            print(f"❌ Error limpiando DynamoDB: {str(e)}")

if __name__ == "__main__":
    collection_id = sys.argv[1] if len(sys.argv) > 1 else 'document-faces-collection'
    
    print("🧹 LIMPIEZA DE COLECCIÓN REKOGNITION")
    print("=" * 50)
    
    cleanup_rekognition_collection(collection_id)
    cleanup_dynamodb_records()
    
    print("\n✅ Proceso de limpieza completado")