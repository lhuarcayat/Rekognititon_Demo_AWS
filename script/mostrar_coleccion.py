#!/usr/bin/env python3
"""
🎯 INSPECTOR DE COLECCIONES REKOGNITION
Script para ver todas las colecciones y rostros indexados
"""

import boto3
import json
from datetime import datetime

def list_rekognition_collections():
    """
    Listar todas las colecciones de Rekognition y sus rostros
    """
    print("🎯 INSPECTOR DE COLECCIONES REKOGNITION")
    print("=" * 60)
    
    rekognition = boto3.client('rekognition')
    
    try:
        # 1. Listar todas las colecciones
        print("📋 OBTENIENDO COLECCIONES...")
        collections_response = rekognition.list_collections()
        
        collections = collections_response.get('CollectionIds', [])
        
        if not collections:
            print("❌ No se encontraron colecciones de Rekognition")
            return
        
        print(f"✅ Encontradas {len(collections)} colecciones")
        print()
        
        # 2. Para cada colección, obtener información detallada
        for i, collection_id in enumerate(collections, 1):
            print(f"📦 COLECCIÓN {i}: {collection_id}")
            print("-" * 50)
            
            try:
                # Información de la colección
                collection_info = rekognition.describe_collection(CollectionId=collection_id)
                
                face_count = collection_info['FaceCount']
                face_model_version = collection_info['FaceModelVersion']
                creation_date = collection_info['CreationTimestamp']
                
                print(f"   📊 Total rostros: {face_count}")
                print(f"   🔢 Versión modelo: {face_model_version}")
                print(f"   📅 Creada: {creation_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
                if face_count > 0:
                    print(f"\n   👥 ROSTROS EN LA COLECCIÓN:")
                    list_faces_in_collection(rekognition, collection_id)
                else:
                    print(f"   📭 Colección vacía")
                    
            except Exception as e:
                print(f"   ❌ Error obteniendo info de colección: {e}")
            
            print()
        
    except Exception as e:
        print(f"❌ Error listando colecciones: {e}")

def list_faces_in_collection(rekognition, collection_id):
    """
    Listar rostros en una colección específica
    """
    try:
        # Paginar a través de todos los rostros
        paginator = rekognition.get_paginator('list_faces')
        face_count = 0
        
        for page in paginator.paginate(CollectionId=collection_id):
            faces = page.get('Faces', [])
            
            for face in faces:
                face_count += 1
                face_id = face['FaceId']
                external_image_id = face.get('ExternalImageId', 'Sin ID')
                confidence = face['Confidence']
                
                # Información adicional si está disponible
                image_id = face.get('ImageId', 'N/A')
                
                print(f"      {face_count}. 🆔 {face_id}")
                print(f"         📝 External ID: {external_image_id}")
                print(f"         🎯 Confianza: {confidence:.1f}%")
                
                if image_id != 'N/A':
                    print(f"         🖼️  Image ID: {image_id}")
                
                # Mostrar solo primeros 10 para no saturar
                if face_count >= 10:
                    remaining = get_total_faces_count(rekognition, collection_id) - 10
                    if remaining > 0:
                        print(f"      ... y {remaining} rostros más")
                    break
            
            if face_count >= 10:
                break
                
    except Exception as e:
        print(f"      ❌ Error listando rostros: {e}")

def get_total_faces_count(rekognition, collection_id):
    """
    Obtener conteo total de rostros en una colección
    """
    try:
        collection_info = rekognition.describe_collection(CollectionId=collection_id)
        return collection_info['FaceCount']
    except:
        return 0

def search_specific_collection(collection_name=None):
    """
    Buscar una colección específica por nombre
    """
    if not collection_name:
        collection_name = input("🔍 Nombre de la colección a buscar: ").strip()
    
    if not collection_name:
        print("❌ Nombre de colección requerido")
        return
    
    print(f"\n🔍 BUSCANDO COLECCIÓN: {collection_name}")
    print("-" * 40)
    
    rekognition = boto3.client('rekognition')
    
    try:
        # Verificar si existe
        collection_info = rekognition.describe_collection(CollectionId=collection_name)
        
        print("✅ Colección encontrada!")
        print(f"   📊 Rostros: {collection_info['FaceCount']}")
        print(f"   🔢 Modelo: {collection_info['FaceModelVersion']}")
        print(f"   📅 Creada: {collection_info['CreationTimestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        if collection_info['FaceCount'] > 0:
            print(f"\n   👥 ROSTROS:")
            list_faces_in_collection(rekognition, collection_name)
            
    except rekognition.exceptions.ResourceNotFoundException:
        print(f"❌ Colección '{collection_name}' no encontrada")
    except Exception as e:
        print(f"❌ Error: {e}")

def get_collection_statistics():
    """
    Obtener estadísticas generales de todas las colecciones
    """
    print("📊 ESTADÍSTICAS GENERALES")
    print("=" * 35)
    
    rekognition = boto3.client('rekognition')
    
    try:
        collections_response = rekognition.list_collections()
        collections = collections_response.get('CollectionIds', [])
        
        if not collections:
            print("❌ No hay colecciones")
            return
        
        total_faces = 0
        collection_stats = []
        
        for collection_id in collections:
            try:
                info = rekognition.describe_collection(CollectionId=collection_id)
                face_count = info['FaceCount']
                total_faces += face_count
                
                collection_stats.append({
                    'name': collection_id,
                    'faces': face_count,
                    'model': info['FaceModelVersion'],
                    'created': info['CreationTimestamp']
                })
                
            except Exception as e:
                print(f"⚠️  Error con {collection_id}: {e}")
        
        # Mostrar estadísticas
        print(f"📦 Total colecciones: {len(collections)}")
        print(f"👥 Total rostros: {total_faces}")
        print(f"📊 Promedio rostros/colección: {total_faces/len(collections):.1f}")
        
        # Top colecciones por número de rostros
        collection_stats.sort(key=lambda x: x['faces'], reverse=True)
        
        print(f"\n🏆 TOP COLECCIONES POR ROSTROS:")
        for i, stats in enumerate(collection_stats[:5], 1):
            print(f"   {i}. {stats['name']}: {stats['faces']} rostros")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def interactive_menu():
    """
    Menú interactivo
    """
    while True:
        print("\n🎮 MENÚ DE OPCIONES")
        print("=" * 30)
        print("1. 📋 Listar todas las colecciones")
        print("2. 🔍 Buscar colección específica")
        print("3. 📊 Ver estadísticas generales")
        print("4. 🎯 Buscar colección del proyecto")
        print("5. ❌ Salir")
        
        choice = input("\nSelecciona opción (1-5): ").strip()
        
        try:
            if choice == '1':
                list_rekognition_collections()
            elif choice == '2':
                search_specific_collection()
            elif choice == '3':
                get_collection_statistics()
            elif choice == '4':
                # Buscar colección típica del proyecto
                search_specific_collection('document-faces-collection')
            elif choice == '5':
                print("👋 ¡Hasta luego!")
                break
            else:
                print("❌ Opción inválida")
                
        except KeyboardInterrupt:
            print("\n👋 ¡Hasta luego!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

def quick_check():
    """
    Verificación rápida de la colección del proyecto
    """
    print("⚡ VERIFICACIÓN RÁPIDA - COLECCIÓN DEL PROYECTO")
    print("=" * 60)
    
    # Colecciones típicas del proyecto
    project_collections = [
        'document-faces-collection',
        'document-faces-collection-v2',
        'basic-dev-faces-collection',
        'dualmode-dev-faces-collection'
    ]
    
    rekognition = boto3.client('rekognition')
    found_any = False
    
    for collection_name in project_collections:
        try:
            info = rekognition.describe_collection(CollectionId=collection_name)
            found_any = True
            
            print(f"✅ ENCONTRADA: {collection_name}")
            print(f"   📊 Rostros: {info['FaceCount']}")
            print(f"   📅 Creada: {info['CreationTimestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            if info['FaceCount'] > 0:
                print(f"   👥 Primeros rostros:")
                try:
                    faces_response = rekognition.list_faces(
                        CollectionId=collection_name,
                        MaxResults=3
                    )
                    
                    for i, face in enumerate(faces_response.get('Faces', []), 1):
                        external_id = face.get('ExternalImageId', 'Sin ID')
                        confidence = face['Confidence']
                        print(f"      {i}. {external_id} ({confidence:.1f}%)")
                        
                except Exception as e:
                    print(f"      ⚠️ Error listando rostros: {e}")
            
            print()
            
        except rekognition.exceptions.ResourceNotFoundException:
            # Colección no existe, continuar
            continue
        except Exception as e:
            print(f"❌ Error verificando {collection_name}: {e}")
    
    if not found_any:
        print("❌ No se encontraron colecciones del proyecto")
        print("💡 Ejecutar: list_rekognition_collections() para ver todas")

def main():
    """
    Función principal
    """
    print("🚀 Iniciando inspector de colecciones...")
    
    # Verificación rápida primero
    quick_check()
    
    # Menú interactivo
    interactive_menu()

if __name__ == "__main__":
    main()