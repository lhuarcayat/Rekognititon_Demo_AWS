import boto3
import json
from typing import List, Dict, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RekognitionCleaner:
    """
    Limpiador completo para colección de Rekognition
    """
    
    def __init__(self, collection_id: str = 'document-faces-collection'):
        self.collection_id = collection_id
        self.rekognition = boto3.client('rekognition')
        self.dynamodb = boto3.resource('dynamodb')
        self.indexed_docs_table = self.dynamodb.Table('rekognition-indexed-documents')
    
    def delete_specific_faces(self, face_ids: List[str], clean_metadata: bool = True) -> Dict:
        """
        Eliminar caras específicas por Face ID
        
        Args:
            face_ids: Lista de Face IDs a eliminar
            clean_metadata: Si limpiar metadatos relacionados en DynamoDB
        """
        print(f"🗑️ Eliminando {len(face_ids)} caras específicas...")
        
        results = {
            'deleted_faces': [],
            'failed_faces': [],
            'cleaned_metadata': []
        }
        
        try:
            # 1. Eliminar caras de Rekognition
            if face_ids:
                response = self.rekognition.delete_faces(
                    CollectionId=self.collection_id,
                    FaceIds=face_ids
                )
                
                results['deleted_faces'] = response.get('DeletedFaces', [])
                results['failed_faces'] = response.get('UnsuccessfulFaceDeletions', [])
                
                print(f"   ✅ Eliminadas de Rekognition: {len(results['deleted_faces'])}")
                if results['failed_faces']:
                    print(f"   ❌ Fallos: {len(results['failed_faces'])}")
            
            # 2. Limpiar metadatos en DynamoDB
            if clean_metadata and results['deleted_faces']:
                for face_id in results['deleted_faces']:
                    try:
                        # Buscar documento por face_id
                        response = self.indexed_docs_table.query(
                            IndexName='face-id-index',
                            KeyConditionExpression='face_id = :fid',
                            ExpressionAttributeValues={':fid': face_id}
                        )
                        
                        for item in response['Items']:
                            # Eliminar metadata
                            self.indexed_docs_table.delete_item(
                                Key={'document_id': item['document_id']}
                            )
                            results['cleaned_metadata'].append(item['document_id'])
                            
                    except Exception as e:
                        logger.error(f"Error limpiando metadata para {face_id}: {e}")
                
                print(f"   🧹 Metadatos limpiados: {len(results['cleaned_metadata'])}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error eliminando caras específicas: {e}")
            raise e
    
    def clear_all_faces(self, confirm: bool = False) -> Dict:
        """
        Limpiar TODAS las caras de la colección (mantener colección)
        
        Args:
            confirm: Confirmación explícita requerida
        """
        if not confirm:
            print("⚠️ PELIGRO: Esta operación eliminará TODAS las caras")
            print("Para confirmar, usa: clear_all_faces(confirm=True)")
            return {'error': 'Confirmación requerida'}
        
        print("🗑️ Limpiando TODAS las caras de la colección...")
        
        try:
            # 1. Obtener todas las caras
            all_faces = self._get_all_faces()
            face_ids = [face['FaceId'] for face in all_faces]
            
            if not face_ids:
                print("ℹ️ No hay caras para eliminar")
                return {'message': 'Colección ya está vacía'}
            
            print(f"   📊 Total de caras a eliminar: {len(face_ids)}")
            
            # 2. Eliminar en lotes (max 4096 por llamada)
            batch_size = 4096
            results = {
                'total_deleted': 0,
                'total_failed': 0,
                'cleaned_metadata': 0
            }
            
            for i in range(0, len(face_ids), batch_size):
                batch = face_ids[i:i + batch_size]
                batch_result = self.delete_specific_faces(batch, clean_metadata=True)
                
                results['total_deleted'] += len(batch_result['deleted_faces'])
                results['total_failed'] += len(batch_result['failed_faces'])
                results['cleaned_metadata'] += len(batch_result['cleaned_metadata'])
            
            # 3. Verificar que la colección está vacía
            remaining_faces = self._get_all_faces()
            
            print(f"\n📊 RESULTADO FINAL:")
            print(f"   ✅ Caras eliminadas: {results['total_deleted']}")
            print(f"   ❌ Fallos: {results['total_failed']}")
            print(f"   🧹 Metadatos limpiados: {results['cleaned_metadata']}")
            print(f"   📋 Caras restantes: {len(remaining_faces)}")
            
            if len(remaining_faces) == 0:
                print("🎉 ¡Colección completamente limpia!")
            
            return results
            
        except Exception as e:
            logger.error(f"Error limpiando todas las caras: {e}")
            raise e
    
    def delete_collection_completely(self, confirm: bool = False) -> Dict:
        """
        Eliminar completamente la colección de Rekognition
        
        Args:
            confirm: Confirmación explícita requerida
        """
        if not confirm:
            print("⚠️ PELIGRO: Esta operación eliminará TODA la colección")
            print("Tendrás que recrearla después")
            print("Para confirmar, usa: delete_collection_completely(confirm=True)")
            return {'error': 'Confirmación requerida'}
        
        print(f"💥 Eliminando colección completa: {self.collection_id}")
        
        try:
            # 1. Verificar que la colección existe
            try:
                self.rekognition.describe_collection(CollectionId=self.collection_id)
            except self.rekognition.exceptions.ResourceNotFoundException:
                print("ℹ️ La colección no existe")
                return {'message': 'Colección no encontrada'}
            
            # 2. Eliminar colección
            response = self.rekognition.delete_collection(CollectionId=self.collection_id)
            
            # 3. Limpiar TODOS los metadatos
            metadata_count = self._clear_all_metadata()
            
            print(f"✅ Colección eliminada: {response['StatusCode']}")
            print(f"🧹 Metadatos limpiados: {metadata_count}")
            print("⚠️ Recuerda recrear la colección antes de indexar nuevas caras")
            
            return {
                'collection_deleted': True,
                'metadata_cleaned': metadata_count,
                'status_code': response['StatusCode']
            }
            
        except Exception as e:
            logger.error(f"Error eliminando colección: {e}")
            raise e
    
    def clean_orphaned_faces(self) -> Dict:
        """
        Limpiar solo caras huérfanas (sin metadata en DynamoDB)
        """
        print("🧹 Limpiando caras huérfanas (sin metadata)...")
        
        try:
            # 1. Obtener todas las caras de Rekognition
            all_faces = self._get_all_faces()
            rekognition_face_ids = {face['FaceId'] for face in all_faces}
            
            # 2. Obtener face_ids con metadata
            response = self.indexed_docs_table.scan()
            metadata_face_ids = {item.get('face_id') for item in response['Items'] if item.get('face_id')}
            
            # 3. Encontrar caras huérfanas
            orphaned_face_ids = list(rekognition_face_ids - metadata_face_ids)
            
            if not orphaned_face_ids:
                print("✅ No hay caras huérfanas")
                return {'message': 'No orphaned faces found'}
            
            print(f"   📊 Caras huérfanas encontradas: {len(orphaned_face_ids)}")
            
            # 4. Eliminar solo caras huérfanas
            result = self.delete_specific_faces(orphaned_face_ids, clean_metadata=False)
            
            print(f"✅ Caras huérfanas eliminadas: {len(result['deleted_faces'])}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error limpiando caras huérfanas: {e}")
            raise e
    
    def get_collection_status(self) -> Dict:
        """
        Obtener estado actual de la colección
        """
        try:
            # 1. Info de la colección
            try:
                collection_info = self.rekognition.describe_collection(CollectionId=self.collection_id)
                collection_exists = True
            except self.rekognition.exceptions.ResourceNotFoundException:
                collection_exists = False
                collection_info = None
            
            # 2. Contar caras
            if collection_exists:
                all_faces = self._get_all_faces()
                face_count = len(all_faces)
            else:
                face_count = 0
            
            # 3. Contar metadatos
            response = self.indexed_docs_table.scan()
            metadata_count = len(response['Items'])
            
            # 4. Detectar inconsistencias
            if collection_exists:
                rekognition_face_ids = {face['FaceId'] for face in all_faces}
                metadata_face_ids = {item.get('face_id') for item in response['Items'] if item.get('face_id')}
                
                orphaned_faces = len(rekognition_face_ids - metadata_face_ids)
                orphaned_metadata = len(metadata_face_ids - rekognition_face_ids)
            else:
                orphaned_faces = 0
                orphaned_metadata = metadata_count
            
            status = {
                'collection_exists': collection_exists,
                'face_count': face_count,
                'metadata_count': metadata_count,
                'orphaned_faces': orphaned_faces,
                'orphaned_metadata': orphaned_metadata,
                'is_consistent': orphaned_faces == 0 and orphaned_metadata == 0
            }
            
            if collection_exists:
                status['collection_info'] = {
                    'creation_timestamp': collection_info['CreationTimestamp'].isoformat(),
                    'face_model_version': collection_info['FaceModelVersion']
                }
            
            return status
            
        except Exception as e:
            logger.error(f"Error obteniendo estado: {e}")
            raise e
    
    def _get_all_faces(self) -> List[Dict]:
        """
        Obtener todas las caras de la colección
        """
        faces = []
        try:
            paginator = self.rekognition.get_paginator('list_faces')
            for page in paginator.paginate(CollectionId=self.collection_id):
                faces.extend(page['Faces'])
        except self.rekognition.exceptions.ResourceNotFoundException:
            pass  # Colección no existe
        return faces
    
    def _clear_all_metadata(self) -> int:
        """
        Limpiar todos los metadatos de DynamoDB
        """
        try:
            response = self.indexed_docs_table.scan()
            items = response['Items']
            
            count = 0
            for item in items:
                self.indexed_docs_table.delete_item(
                    Key={'document_id': item['document_id']}
                )
                count += 1
            
            return count
            
        except Exception as e:
            logger.error(f"Error limpiando metadatos: {e}")
            return 0


def main():
    """
    Función principal con menú interactivo
    """
    cleaner = RekognitionCleaner()
    
    print("🧹 LIMPIADOR DE COLECCIÓN REKOGNITION")
    print("=" * 50)
    
    # Mostrar estado actual
    status = cleaner.get_collection_status()
    
    print("📊 ESTADO ACTUAL:")
    print(f"   Colección existe: {'✅' if status['collection_exists'] else '❌'}")
    print(f"   Caras en Rekognition: {status['face_count']}")
    print(f"   Metadatos en DynamoDB: {status['metadata_count']}")
    print(f"   Caras huérfanas: {status['orphaned_faces']}")
    print(f"   Metadatos huérfanos: {status['orphaned_metadata']}")
    print(f"   Sistema consistente: {'✅' if status['is_consistent'] else '❌'}")
    
    if not status['collection_exists']:
        print("\n❌ No hay colección para limpiar")
        return
    
    if status['face_count'] == 0:
        print("\n✅ La colección ya está vacía")
        return
    
    print(f"\n🛠️ OPCIONES DISPONIBLES:")
    print(f"   1. 🧹 Limpiar solo caras huérfanas ({status['orphaned_faces']})")
    print(f"   2. 🗑️ Vaciar toda la colección ({status['face_count']} caras)")
    print(f"   3. 💥 Eliminar colección completa")
    print(f"   4. ❌ Cancelar")
    
    try:
        choice = input(f"\nSelecciona una opción (1-4): ").strip()
        
        if choice == '1':
            if status['orphaned_faces'] > 0:
                result = cleaner.clean_orphaned_faces()
                print(f"✅ Operación completada")
            else:
                print("ℹ️ No hay caras huérfanas para limpiar")
                
        elif choice == '2':
            confirm = input("⚠️ ¿Confirmas vaciar TODA la colección? (y/N): ").lower() == 'y'
            if confirm:
                result = cleaner.clear_all_faces(confirm=True)
                print(f"✅ Colección vaciada")
            else:
                print("❌ Operación cancelada")
                
        elif choice == '3':
            confirm = input("⚠️ ¿Confirmas ELIMINAR la colección completa? (y/N): ").lower() == 'y'
            if confirm:
                result = cleaner.delete_collection_completely(confirm=True)
                print(f"✅ Colección eliminada completamente")
            else:
                print("❌ Operación cancelada")
                
        elif choice == '4':
            print("❌ Operación cancelada")
            
        else:
            print("❌ Opción inválida")
            
    except KeyboardInterrupt:
        print("\n❌ Operación cancelada por el usuario")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Ejemplos de uso:
    
    # 1. Crear instancia del limpiador
    cleaner = RekognitionCleaner()
    
    # 2. Ver estado actual
    #status = cleaner.get_collection_status()
    #print(json.dumps(status, indent=2, default=str))
    
    # 3. Limpiar solo huérfanas
    # result = cleaner.clean_orphaned_faces()
    
    # 4. Vaciar toda la colección
    # result = cleaner.clear_all_faces(confirm=True)
    
    # 5. Eliminar colección completa
    # result = cleaner.delete_collection_completely(confirm=True)
    
    # 6. Eliminar caras específicas
    # face_ids = ['face-id-1', 'face-id-2']
    # result = cleaner.delete_specific_faces(face_ids)
    
    # Ejecutar menú interactivo
    main()
