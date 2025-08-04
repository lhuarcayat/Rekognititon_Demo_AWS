import boto3
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger()

class RekognitionClient:
    """
    Cliente Rekognition CORREGIDO que SIEMPRE obtiene similarity real
    """
    
    def __init__(self, collection_id: str):
        self.rekognition = boto3.client('rekognition')
        self.collection_id = collection_id
    
    def create_collection_if_not_exists(self) -> bool:
        """Crear colección si no existe"""
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
    
    def compare_faces(self, source_image: bytes, target_image: bytes, threshold: float = 80.0) -> Dict:
        """
        🔧 MÉTODO CORREGIDO: SIEMPRE obtiene similarity real
        
        ESTRATEGIA: Hacer DOS llamadas si es necesario
        1. Primera llamada con threshold BAJO (0) para obtener similarity real
        2. Evaluar internamente si sería un "match" con el threshold deseado
        """
        try:
            # Validar parámetros
            if threshold < 0 or threshold > 100:
                return {
                    'success': False, 
                    'error': f'Invalid threshold: {threshold}. Must be between 0 and 100'
                }
            
            logger.info(f"🔧 FIXED: Comparing faces to get REAL similarity (threshold bypass)")
            
            # 🎯 SOLUCIÓN: Usar threshold=0 para SIEMPRE obtener similarity
            response = self.rekognition.compare_faces(
                SourceImage={'Bytes': source_image},
                TargetImage={'Bytes': target_image},
                SimilarityThreshold=0  # ← CLAVE: threshold=0 captura TODO
            )
            
            # Procesar respuesta
            source_face = response.get('SourceImageFace', {})
            all_faces = response.get('FaceMatches', []) + response.get('UnmatchedFaces', [])
            
            logger.info(f"Found {len(all_faces)} faces in target image")
            
            if not all_faces:
                # No hay caras en la imagen objetivo
                return {
                    'success': True,
                    'match_found': False,
                    'similarity': 0,
                    'confidence': 0,
                    'source_face_detected': bool(source_face),
                    'target_faces_detected': 0,
                    'details': {
                        'reason': 'No faces detected in target image',
                        'source_face_confidence': source_face.get('Confidence', 0)
                    }
                }
            
            # 🎯 OBTENER SIMILARITY REAL de la mejor cara
            best_similarity = 0
            best_face_confidence = 0
            best_face_details = {}
            
            # Revisar FaceMatches (tienen similarity directamente)
            for face_match in response.get('FaceMatches', []):
                similarity = face_match['Similarity']
                face_confidence = face_match['Face']['Confidence']
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_face_confidence = face_confidence
                    best_face_details = face_match['Face']
                    
                logger.info(f"Face match found: {similarity:.2f}% similarity")
            
            # Revisar UnmatchedFaces (NO tienen similarity, pero podemos inferir que es baja)
            for unmatched_face in response.get('UnmatchedFaces', []):
                face_confidence = unmatched_face['Confidence']
                # Para UnmatchedFaces, similarity es desconocida pero < threshold original
                # Como usamos threshold=0, esto NO debería pasar, pero por si acaso
                logger.info(f"Unmatched face detected with {face_confidence:.1f}% confidence")
            
            # 🎯 EVALUAR match_found BASADO EN EL THRESHOLD DESEADO
            # Ahora YA TENEMOS el similarity real, podemos aplicar nuestra lógica
            would_be_match = best_similarity >= threshold
            
            logger.info(f"Real similarity: {best_similarity:.2f}%")
            logger.info(f"Desired threshold: {threshold}%")
            logger.info(f"Would be match: {would_be_match}")
            
            return {
                'success': True,
                'match_found': would_be_match,  # ← Basado en NUESTRO threshold
                'similarity': best_similarity,   # ← SIEMPRE el valor real
                'confidence': best_face_confidence,
                'source_face_detected': bool(source_face),
                'target_faces_detected': len(all_faces),
                'details': {
                    'original_threshold_bypassed': True,
                    'real_threshold_applied': threshold,
                    'source_face_confidence': source_face.get('Confidence', 0),
                    'best_face_bounding_box': best_face_details.get('BoundingBox', {}),
                    'total_faces_evaluated': len(all_faces)
                }
            }
            
        except self.rekognition.exceptions.InvalidParameterException as e:
            error_msg = str(e)
            logger.error(f"InvalidParameterException: {error_msg}")
            
            if 'image' in error_msg.lower():
                if 'format' in error_msg.lower():
                    return {
                        'success': False,
                        'error': 'Invalid image format. Only JPEG and PNG are supported.',
                        'error_type': 'INVALID_FORMAT'
                    }
                elif 'size' in error_msg.lower():
                    return {
                        'success': False,
                        'error': 'Image size invalid. Must be between 80x80 and 4096x4096 pixels.',
                        'error_type': 'INVALID_SIZE'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Image parameter invalid: {error_msg}',
                        'error_type': 'INVALID_IMAGE'
                    }
            else:
                return {
                    'success': False,
                    'error': f'Invalid parameters: {error_msg}',
                    'error_type': 'INVALID_PARAMETERS'
                }
                
        except Exception as e:
            logger.error(f"Unexpected error comparing faces: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'error_type': 'UNEXPECTED_ERROR'
            }
    
    def index_face(self, image_bytes: bytes, external_image_id: str) -> Dict:
        """Indexar cara en la colección"""
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
                'confidence': face_record['Face']['Confidence'],
                'bounding_box': face_record['Face']['BoundingBox']
            }
            
        except Exception as e:
            logger.error(f"Error indexing face: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def search_faces_by_image(self, image_bytes: bytes, threshold: float = 80.0, max_faces: int = 5) -> Dict:
        """Buscar caras similares en la colección"""
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
    
    def detect_faces(self, image_bytes: bytes) -> Dict:
        """Detectar caras para validación de calidad"""
        try:
            # Validar tamaño
            if len(image_bytes) > 15 * 1024 * 1024:
                return {
                    'success': False,
                    'error': f'Image too large: {len(image_bytes)/1024/1024:.1f}MB (max: 15MB)'
                }
            
            response = self.rekognition.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['DEFAULT']
            )
            
            face_count = len(response['FaceDetails'])
            logger.info(f"Detected {face_count} faces in image")
            
            return {
                'success': True,
                'face_count': face_count,
                'faces': response['FaceDetails']
            }
            
        except self.rekognition.exceptions.InvalidParameterException as e:
            return {
                'success': False,
                'error': f'Invalid image parameters: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Error detecting faces: {str(e)}")
            return {'success': False, 'error': str(e)}