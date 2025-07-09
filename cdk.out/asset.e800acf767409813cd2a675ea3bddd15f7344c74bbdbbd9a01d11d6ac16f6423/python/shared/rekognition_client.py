import boto3
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger()

class RekognitionClient:
    """
    Cliente optimizado para operaciones Rekognition
    """
    
    def __init__(self, collection_id: str):
        self.rekognition = boto3.client('rekognition')
        self.collection_id = collection_id
    
    def create_collection_if_not_exists(self) -> bool:
        """
        Crear colección si no existe
        """
        try:
            self.rekognition.describe_collection(CollectionId=self.collection_id)
            logger.info(f"Collection {self.collection_id} already exists")
            return True
        except self.rekognition.exceptions.ResourceNotFoundException:
            try:
                self.rekognition.create_collection(CollectionId=self.collection_id)
                logger.info(f"Created collection {self.collection_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to create collection: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Error checking collection: {str(e)}")
            return False
    
    def index_face(self, image_bytes: bytes, external_image_id: str) -> Dict:
        """
        Indexar cara en la colección
        """
        try:
            response = self.rekognition.index_faces(
                CollectionId=self.collection_id,
                Image={'Bytes': image_bytes},
                ExternalImageId=external_image_id,
                MaxFaces=1,
                QualityFilter='AUTO',
                DetectionAttributes=['DEFAULT']
            )
            
            if not response['FaceRecords']:
                return {'success': False, 'error': 'No faces detected in image'}
                
            face_record = response['FaceRecords'][0]
            return {
                'success': True,
                'face_id': face_record['Face']['FaceId'],
                'image_id':face_record['Face']['ImageId'],
                'confidence': face_record['Face']['Confidence'],
                'bounding_box': face_record['Face']['BoundingBox'],
                'collection_id':self.collection_id
            }
            
        except Exception as e:
            logger.error(f"Error indexing face: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def search_faces_by_image(self, image_bytes: bytes, threshold: float = 80.0, max_faces: int = 5) -> Dict:
        """
        Buscar caras similares en la colección
        """
        try:
            response = self.rekognition.search_faces_by_image(
                CollectionId=self.collection_id,
                Image={'Bytes': image_bytes},
                FaceMatchThreshold=threshold,
                MaxFaces=max_faces
            )
            
            return {
                'success': True,
                'face_matches': response['FaceMatches'],
                'searched_face': response.get('SearchedFaceBoundingBox', {})
            }
            
        except Exception as e:
            logger.error(f"Error searching faces: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def compare_faces(self, source_image: bytes, target_image: bytes, threshold: float = 80.0) -> Dict:
        """
        Comparar dos imágenes cara a cara
        """
        try:
            response = self.rekognition.compare_faces(
                SourceImage={'Bytes': source_image},
                TargetImage={'Bytes': target_image},
                SimilarityThreshold=threshold
            )
            
            if not response['FaceMatches']:
                return {
                    'success': True,
                    'match_found': False,
                    'similarity': 0,
                    'confidence': 0
                }
            
            best_match = response['FaceMatches'][0]
            return {
                'success': True,
                'match_found': True,
                'similarity': best_match['Similarity'],
                'confidence': best_match['Face']['Confidence']
            }
            
        except Exception as e:
            logger.error(f"Error comparing faces: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def detect_faces(self, image_bytes: bytes) -> Dict:
        """
        Detectar caras para validación de calidad
        """
        try:
            response = self.rekognition.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['DEFAULT']
            )
            
            return {
                'success': True,
                'face_count': len(response['FaceDetails']),
                'faces': response['FaceDetails']
            }
            
        except Exception as e:
            logger.error(f"Error detecting faces: {str(e)}")
            return {'success': False, 'error': str(e)}