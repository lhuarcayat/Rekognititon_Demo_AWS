import boto3
import io
from PIL import Image, ExifTags
import logging

logger=logging.getLogger()
logger.setLevel(logging.INFO)

class MinimalImageProcessor:
    def __init__(self):
        self.MAX_FILE_SIZE =15*1024*1024
        self.MIN_DIMENSION=80
        self.MAX_DIMENSION=4096
        self.SUPPORTED_FORMATS=['JPEG','PNG']

    def process_image(self,image_bytes:bytes,filename:str)->tuple:
        try:
            if len(image_bytes) > self.MAX_FILE_SIZE:
                logger.error(f"File {filename} exceeds 15MB limit: {len(image_bytes)/1024/1024:.1f}MB")
                return None, f"File too large: {len(image_bytes)/1024/1024:.1f}MB (max: 15MB)"
            try:
                image = Image.open(io.BytesIO(image_bytes))
            except Exception as e:
                return None, f"Invalid image format: {str(e)}"    
            if image.format not in self.SUPPORTED_FORMATS:
                return None, f"Unsupported format: {image.format}. Supported: {self.SUPPORTED_FORMATS}"
            image = self._fix_orientation(image)
            width, height = image.size
            if width < self.MIN_DIMENSION or height < self.MIN_DIMENSION:
                return None, f"Image too small: {width}x{height} (min: {self.MIN_DIMENSION}x{self.MIN_DIMENSION})"
            if width > self.MAX_DIMENSION or height > self.MAX_DIMENSION:
                image=self._resize_image(image)
                logger.info(f"Resized image from {width}x{height} to {image.size}")
            output_buffer = io.BytesIO()
            if image.format == 'PNG':
                # Convertir PNG a JPEG para mejor compresión
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                rgb_image.save(output_buffer, format='JPEG', quality=85, optimize=True)
            else:
                image.save(output_buffer, format='JPEG', quality=85, optimize=True)
                
            processed_bytes = output_buffer.getvalue()
            if len(processed_bytes) > self.MAX_FILE_SIZE:
                return None, f"Unable to compress image below 15MB limit"
            logger.info(f"Processed {filename}: {len(image_bytes)/1024/1024:.1f}MB → {len(processed_bytes)/1024/1024:.1f}MB")
            return processed_bytes, None
        except Exception as e:
            logger.error(f'Error processing {filename}:{str(e)}')
            return None, f'Processing failed: {str(e)}'
    
    def _fix_orientation(self, image):
        """
        Corrige orientación basada en EXIF - CRÍTICO para fotos de móviles
        """
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
                    
            exif = image._getexif()
            if exif is not None:
                orientation_value = exif.get(orientation)
                
                if orientation_value == 3:
                    image = image.rotate(180, expand=True)
                elif orientation_value == 6:
                    image = image.rotate(270, expand=True)
                elif orientation_value == 8:
                    image = image.rotate(90, expand=True)
                    
        except (AttributeError, KeyError, TypeError):
            # No EXIF data available, skip orientation fix
            pass
            
        return image
    
    def _resize_image(self, image):
        """
        Redimensiona imagen manteniendo aspect ratio
        """
        width, height = image.size
        
        if width > height:
            new_width = self.MAX_DIMENSION
            new_height = int((height * self.MAX_DIMENSION) / width)
        else:
            new_height = self.MAX_DIMENSION  
            new_width = int((width * self.MAX_DIMENSION) / height)
            
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)











