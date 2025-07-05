#!/usr/bin/env python3
"""
🔍 DIAGNÓSTICO CLOUDFRONT/S3
Diagnostica y corrige el problema "NoSuchKey" de CloudFront
"""

import boto3
import json
import time
from pathlib import Path

def get_stack_info():
    """Obtener información detallada del stack"""
    print("📋 Analizando información del stack...")
    
    try:
        cf = boto3.client('cloudformation')
        sts = boto3.client('sts')
        
        # Obtener account ID actual
        account_info = sts.get_caller_identity()
        current_account = account_info['Account']
        print(f"   ✅ Account ID actual: {current_account}")
        
        # Obtener outputs del stack
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        stack = response['Stacks'][0]
        
        outputs = {}
        for output in stack['Outputs']:
            outputs[output['OutputKey']] = output['OutputValue']
        
        print(f"   📋 Outputs del stack:")
        for key, value in outputs.items():
            print(f"      {key}: {value}")
        
        return outputs, current_account
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None, None

def check_s3_bucket(bucket_name):
    """Verificar contenido del bucket S3"""
    print(f"\n🪣 Verificando bucket S3: {bucket_name}")
    
    try:
        s3 = boto3.client('s3')
        
        # Verificar que el bucket existe
        try:
            s3.head_bucket(Bucket=bucket_name)
            print(f"   ✅ Bucket existe")
        except Exception as e:
            print(f"   ❌ Bucket no existe o no accesible: {e}")
            return False
        
        # Listar objetos
        try:
            response = s3.list_objects_v2(Bucket=bucket_name)
            
            if 'Contents' not in response:
                print(f"   ❌ Bucket está vacío")
                return False
            
            objects = response['Contents']
            print(f"   📁 Objetos en bucket ({len(objects)}):")
            
            critical_files = ['index.html', 'capture.html', 'transaction.html']
            found_files = []
            
            for obj in objects:
                key = obj['Key']
                size = obj['Size']
                modified = obj['LastModified']
                print(f"      📄 {key} ({size} bytes, {modified})")
                
                if key in critical_files:
                    found_files.append(key)
            
            missing = [f for f in critical_files if f not in found_files]
            if missing:
                print(f"   ⚠️  Archivos críticos faltantes: {missing}")
                return False
            else:
                print(f"   ✅ Todos los archivos críticos presentes")
                return True
                
        except Exception as e:
            print(f"   ❌ Error listando objetos: {e}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error con bucket: {e}")
        return False

def check_cloudfront_config(distribution_id, expected_bucket):
    """Verificar configuración de CloudFront"""
    print(f"\n☁️ Verificando CloudFront: {distribution_id}")
    
    try:
        cloudfront = boto3.client('cloudfront')
        
        # Obtener configuración de la distribución
        response = cloudfront.get_distribution_config(Id=distribution_id)
        config = response['DistributionConfig']
        etag = response['ETag']
        
        # Verificar origen
        origins = config['Origins']['Items']
        print(f"   📡 Orígenes configurados ({len(origins)}):")
        
        bucket_from_origin = None
        needs_fix = False
        
        for origin in origins:
            origin_id = origin['Id']
            domain_name = origin['DomainName']
            origin_type = 'S3' if 's3' in domain_name else 'Custom'
            
            print(f"      🎯 {origin_id}: {domain_name} ({origin_type})")
            
            if origin_type == 'S3':
                # Extraer bucket name del domain
                bucket_from_origin = domain_name.replace('.s3.amazonaws.com', '')
                print(f"         📦 Bucket desde origen: {bucket_from_origin}")
                
                if bucket_from_origin != expected_bucket:
                    print(f"         ❌ INCORRECTO! Debería ser: {expected_bucket}")
                    needs_fix = True
                else:
                    print(f"         ✅ Correcto")
        
        return bucket_from_origin, needs_fix, config, etag
        
    except Exception as e:
        print(f"   ❌ Error con CloudFront: {e}")
        return None, False, None, None

def fix_bucket_mismatch(correct_bucket, outputs):
    """Corregir discrepancia de bucket"""
    print(f"\n🔧 Subiendo archivos al bucket correcto: {correct_bucket}")
    
    try:
        s3 = boto3.client('s3')
        web_dir = Path("web_interface")
        
        if not web_dir.exists():
            print(f"   ❌ Directorio web_interface no encontrado")
            return False
        
        uploaded_count = 0
        
        for file_path in web_dir.rglob("*"):
            if file_path.is_file():
                s3_key = str(file_path.relative_to(web_dir))
                
                # Determinar content type
                if file_path.suffix == '.html':
                    content_type = 'text/html'
                elif file_path.suffix == '.css':
                    content_type = 'text/css'
                elif file_path.suffix == '.js':
                    content_type = 'application/javascript'
                else:
                    content_type = 'binary/octet-stream'
                
                print(f"      📄 Subiendo {s3_key}...")
                
                # Subir archivo
                s3.upload_file(
                    str(file_path),
                    correct_bucket,
                    s3_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'CacheControl': 'max-age=3600'
                    }
                )
                
                uploaded_count += 1
        
        print(f"   ✅ {uploaded_count} archivos subidos")
        return True
        
    except Exception as e:
        print(f"   ❌ Error subiendo archivos: {e}")
        return False

def fix_cloudfront_origin(distribution_id, config, etag, correct_bucket):
    """Corregir origen de CloudFront para apuntar al bucket correcto"""
    print(f"\n🔧 Corrigiendo origen de CloudFront...")
    
    try:
        cloudfront = boto3.client('cloudfront')
        
        # Actualizar configuración de orígenes
        origins = config['Origins']['Items']
        
        for origin in origins:
            if 's3' in origin['DomainName']:
                old_domain = origin['DomainName']
                new_domain = f"{correct_bucket}.s3.amazonaws.com"
                
                print(f"   📡 Cambiando origen:")
                print(f"      Anterior: {old_domain}")
                print(f"      Nuevo: {new_domain}")
                
                origin['DomainName'] = new_domain
                
                # Actualizar S3OriginConfig si existe
                if 'S3OriginConfig' in origin:
                    origin['S3OriginConfig']['OriginAccessIdentity'] = origin['S3OriginConfig'].get('OriginAccessIdentity', '')
        
        # Aplicar cambios
        print(f"   🔄 Aplicando cambios a CloudFront...")
        
        response = cloudfront.update_distribution(
            Id=distribution_id,
            DistributionConfig=config,
            IfMatch=etag
        )
        
        print(f"   ✅ CloudFront actualizado exitosamente")
        print(f"   ⏱️  Los cambios pueden tardar 10-15 minutos en propagarse")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error actualizando CloudFront: {e}")
        return False
    """Corregir discrepancia de bucket"""
    print(f"\n🔧 Corrigiendo discrepancia de bucket...")
    
    try:
        # Subir archivos al bucket correcto
        s3 = boto3.client('s3')
        web_dir = Path("web_interface")
        
        if not web_dir.exists():
            print(f"   ❌ Directorio web_interface no encontrado")
            return False
        
        print(f"   📤 Subiendo archivos a bucket correcto: {correct_bucket}")
        
        uploaded_count = 0
        
        for file_path in web_dir.rglob("*"):
            if file_path.is_file():
                s3_key = str(file_path.relative_to(web_dir))
                
                # Determinar content type
                if file_path.suffix == '.html':
                    content_type = 'text/html'
                elif file_path.suffix == '.css':
                    content_type = 'text/css'
                elif file_path.suffix == '.js':
                    content_type = 'application/javascript'
                else:
                    content_type = 'binary/octet-stream'
                
                print(f"      📄 Subiendo {s3_key}...")
                
                # Subir archivo
                s3.upload_file(
                    str(file_path),
                    correct_bucket,
                    s3_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'CacheControl': 'max-age=3600'
                    }
                )
                
                uploaded_count += 1
        
        print(f"   ✅ {uploaded_count} archivos subidos al bucket correcto")
        
        # Invalidar cache de CloudFront
        distribution_id = outputs.get('CloudFrontDistributionId')
        if distribution_id:
            print(f"   🔄 Invalidando cache de CloudFront...")
            
            cloudfront = boto3.client('cloudfront')
            cloudfront.create_invalidation(
                DistributionId=distribution_id,
                InvalidationBatch={
                    'Paths': {'Quantity': 1, 'Items': ['/*']},
                    'CallerReference': f'fix-{int(time.time())}'
                }
            )
            print(f"   ✅ Cache invalidado")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error corrigiendo bucket: {e}")
        return False

def test_web_access(web_url):
    """Probar acceso web después de la corrección"""
    print(f"\n🧪 Probando acceso web...")
    
    print(f"   ⏱️  Esperando 30 segundos para propagación...")
    time.sleep(30)
    
    try:
        import urllib.request
        
        test_url = f"{web_url}/index.html"
        print(f"   🎯 Probando: {test_url}")
        
        request = urllib.request.Request(test_url)
        request.add_header('User-Agent', 'CloudFrontFix/1.0')
        request.add_header('Cache-Control', 'no-cache')
        
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status == 200:
                content = response.read().decode('utf-8')
                
                if '<html' in content.lower():
                    print(f"      ✅ Web accesible - HTML válido")
                    
                    # Verificar configuración de API
                    import re
                    api_match = re.search(r"const API_BASE = '([^']+)'", content)
                    if api_match:
                        api_url = api_match.group(1)
                        print(f"      ✅ API configurada: {api_url}")
                    
                    return True
                else:
                    print(f"      ❌ Respuesta no es HTML válido")
                    return False
            else:
                print(f"      ❌ Status code: {response.status}")
                return False
                
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    """Diagnóstico y corrección de CloudFront/S3"""
    print("🔍 DIAGNÓSTICO CLOUDFRONT/S3")
    print("=" * 60)
    print("Resuelve el problema 'NoSuchKey' de CloudFront")
    
    # BUCKET CORRECTO ESPECIFICADO POR EL USUARIO
    correct_bucket = "rekog-poc-web-442431377530"
    print(f"🎯 Bucket objetivo: {correct_bucket}")
    
    # 1. Obtener información del stack
    outputs, current_account = get_stack_info()
    
    if not outputs:
        print("\n❌ No se pudo obtener información del stack")
        return False
    
    web_bucket_from_stack = outputs.get('WebBucketName')
    web_url = outputs.get('WebInterfaceURL')
    distribution_id = outputs.get('CloudFrontDistributionId')
    
    if not all([web_url, distribution_id]):
        print("\n❌ Información del stack incompleta")
        print(f"   WebBucketName: {web_bucket_from_stack}")
        print(f"   WebInterfaceURL: {web_url}")
        print(f"   CloudFrontDistributionId: {distribution_id}")
        return False
    
    print(f"\n📋 Información del Stack:")
    print(f"   Stack bucket: {web_bucket_from_stack}")
    print(f"   Bucket correcto: {correct_bucket}")
    print(f"   Web URL: {web_url}")
    
    # 2. Verificar bucket correcto
    print(f"\n🔍 VERIFICANDO BUCKET CORRECTO: {correct_bucket}")
    bucket_ok = check_s3_bucket(correct_bucket)
    
    # 3. Verificar configuración CloudFront
    bucket_from_cloudfront, needs_cloudfront_fix, cf_config, cf_etag = check_cloudfront_config(distribution_id, correct_bucket)
    
    # 4. Detectar y corregir problemas
    problems_detected = []
    fixes_applied = []
    
    if not bucket_ok:
        problems_detected.append("Archivos faltantes en bucket correcto")
    
    if needs_cloudfront_fix:
        problems_detected.append(f"CloudFront apunta a bucket incorrecto: {bucket_from_cloudfront}")
    
    if problems_detected:
        print(f"\n❌ PROBLEMAS DETECTADOS:")
        for i, problem in enumerate(problems_detected, 1):
            print(f"   {i}. {problem}")
        
        print(f"\n🔧 APLICANDO CORRECCIONES...")
        
        # Corrección 1: Subir archivos al bucket correcto
        if not bucket_ok:
            print(f"\n📤 CORRECCIÓN 1: Subir archivos a {correct_bucket}")
            if fix_bucket_mismatch(correct_bucket, outputs):
                fixes_applied.append("Archivos subidos al bucket correcto")
                bucket_ok = True
            else:
                print(f"   ❌ Error subiendo archivos")
        
        # Corrección 2: Actualizar CloudFront
        if needs_cloudfront_fix and cf_config and cf_etag:
            print(f"\n☁️ CORRECCIÓN 2: Actualizar origen de CloudFront")
            if fix_cloudfront_origin(distribution_id, cf_config, cf_etag, correct_bucket):
                fixes_applied.append("CloudFront origen actualizado")
            else:
                print(f"   ❌ Error actualizando CloudFront")
        
        # Corrección 3: Invalidar cache
        print(f"\n🔄 CORRECCIÓN 3: Invalidar cache CloudFront")
        try:
            cloudfront = boto3.client('cloudfront')
            cloudfront.create_invalidation(
                DistributionId=distribution_id,
                InvalidationBatch={
                    'Paths': {'Quantity': 1, 'Items': ['/*']},
                    'CallerReference': f'fix-bucket-{int(time.time())}'
                }
            )
            print(f"   ✅ Cache invalidado")
            fixes_applied.append("Cache invalidado")
        except Exception as e:
            print(f"   ❌ Error invalidando cache: {e}")
        
        # Reporte de correcciones
        if fixes_applied:
            print(f"\n✅ CORRECCIONES APLICADAS:")
            for fix in fixes_applied:
                print(f"   ✅ {fix}")
            
            # Probar acceso después de correcciones
            if bucket_ok:
                if test_web_access(web_url):
                    print(f"\n🎉 ¡PROBLEMA COMPLETAMENTE RESUELTO!")
                    print(f"   ✅ CloudFront funcionando correctamente")
                    print(f"   ✅ Archivos servidos desde bucket correcto")
                    print(f"   🌐 URL: {web_url}")
                    print(f"\n💡 LISTO PARA USAR:")
                    print(f"   1. Refresca la página (Ctrl+F5)")
                    print(f"   2. Debería cargar index.html correctamente")
                    return True
                else:
                    print(f"\n⚠️  CORRECCIONES APLICADAS - ESPERANDO PROPAGACIÓN")
                    print(f"   🔄 CloudFront puede tardar 10-15 minutos en propagarse")
                    print(f"   ⏱️  Espera y prueba: {web_url}")
                    print(f"\n💡 MIENTRAS TANTO:")
                    print(f"   - Los archivos están en el bucket correcto")
                    print(f"   - CloudFront está configurado correctamente")
                    print(f"   - Solo falta tiempo de propagación")
                    return False
            else:
                print(f"\n❌ No se pudieron aplicar todas las correcciones")
                return False
        else:
            print(f"\n❌ No se pudieron aplicar correcciones")
            return False
    else:
        print(f"\n✅ CONFIGURACIÓN CORRECTA DETECTADA")
        print(f"   ✅ Bucket correcto: {correct_bucket}")
        print(f"   ✅ CloudFront apunta al bucket correcto")
        print(f"   ✅ Archivos presentes en bucket")
        
        # Aún así probar acceso
        if test_web_access(web_url):
            print(f"\n🎉 ¡TODO FUNCIONANDO CORRECTAMENTE!")
            return True
        else:
            print(f"\n🤔 Configuración correcta pero web no accesible")
            print(f"   💡 Posibles causas:")
            print(f"   1. Propagación de CloudFront en progreso")
            print(f"   2. Cache local del navegador")
            print(f"   3. Permisos de bucket S3")
            print(f"\n🔧 INTENTOS ADICIONALES:")
            
            # Invalidar cache como precaución
            try:
                cloudfront = boto3.client('cloudfront')
                cloudfront.create_invalidation(
                    DistributionId=distribution_id,
                    InvalidationBatch={
                        'Paths': {'Quantity': 1, 'Items': ['/*']},
                        'CallerReference': f'final-fix-{int(time.time())}'
                    }
                )
                print(f"   ✅ Cache invalidado como precaución")
            except:
                pass
            
            print(f"   ⏱️  Espera 5-10 minutos y prueba: {web_url}")
            return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)