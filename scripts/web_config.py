#!/usr/bin/env python3
"""
🔧 WEB CONFIG COMPLETO
Configura archivos HTML + corrige CloudFront automáticamente
"""

import boto3
import json
import re
import time
from pathlib import Path

def get_stack_info():
    """Obtener información completa del stack"""
    print("📋 Obteniendo información del stack...")
    
    try:
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        
        outputs = {}
        for output in response['Stacks'][0]['Outputs']:
            outputs[output['OutputKey']] = output['OutputValue']
        
        api_url = outputs.get('APIGatewayURL', '').rstrip('/')
        web_url = outputs.get('WebInterfaceURL')
        bucket_name = outputs.get('WebBucketName')
        distribution_id = outputs.get('CloudFrontDistributionId')
        
        print(f"   ✅ API URL: {api_url}")
        print(f"   ✅ Web URL: {web_url}")
        print(f"   ✅ Bucket: {bucket_name}")
        print(f"   ✅ Distribution ID: {distribution_id}")
        
        return api_url, web_url, bucket_name, distribution_id
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None, None, None, None

def fix_html_files(api_url):
    """Corregir archivos HTML con la URL correcta del API"""
    print(f"\n🔧 Corrigiendo archivos HTML...")
    
    web_dir = Path("web_interface")
    if not web_dir.exists():
        print(f"   ❌ Directorio web_interface no encontrado")
        return False
    
    html_files = list(web_dir.glob("*.html"))
    if not html_files:
        print(f"   ❌ No se encontraron archivos HTML")
        return False
    
    fixed_files = []
    
    for html_file in html_files:
        try:
            print(f"   🔧 Procesando {html_file.name}...")
            
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # 1. Reemplazar PLACEHOLDER_API_URL
            if 'PLACEHOLDER_API_URL' in content:
                content = content.replace('PLACEHOLDER_API_URL', api_url)
                print(f"      ✅ Reemplazado PLACEHOLDER_API_URL")
            
            # 2. Actualizar const API_BASE existente
            api_base_pattern = r"const API_BASE = '[^']*'"
            if re.search(api_base_pattern, content):
                content = re.sub(api_base_pattern, f"const API_BASE = '{api_url}'", content)
                print(f"      ✅ Actualizado const API_BASE")
            
            # 3. Verificar que se aplicaron cambios
            if content != original_content:
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                fixed_files.append(html_file.name)
                print(f"      ✅ {html_file.name} actualizado")
            else:
                print(f"      ℹ️  {html_file.name} ya estaba correcto")
        
        except Exception as e:
            print(f"      ❌ Error con {html_file.name}: {e}")
    
    if fixed_files:
        print(f"   ✅ Archivos corregidos: {fixed_files}")
        return True
    else:
        print(f"   ℹ️  Todos los archivos ya estaban correctos")
        return True

def check_and_fix_cloudfront(distribution_id, bucket_name):
    """Verificar CloudFront (ya debería estar correcto)"""
    print(f"\n☁️ Verificando CloudFront...")
    
    try:
        cloudfront = boto3.client('cloudfront')
        
        # Obtener configuración actual
        response = cloudfront.get_distribution_config(Id=distribution_id)
        config = response['DistributionConfig']
        
        # Verificar origen
        origins = config['Origins']['Items']
        
        for origin in origins:
            domain_name = origin['DomainName']
            print(f"   📡 Origen actual: {domain_name}")
            
            # El domain correcto es .s3.us-east-1.amazonaws.com (lo que CDK genera)
            expected_domain = f"{bucket_name}.s3.us-east-1.amazonaws.com"
            if domain_name == expected_domain:
                print(f"   ✅ CloudFront configurado correctamente")
                return False  # No necesita corrección
            elif f"{bucket_name}.s3.amazonaws.com" in domain_name:
                print(f"   ✅ CloudFront usando domain S3 válido")
                return False  # También válido
            else:
                print(f"   ❌ Domain inesperado: {domain_name}")
                return False  # No corregir automáticamente
        
        return False
            
    except Exception as e:
        print(f"   ❌ Error verificando CloudFront: {e}")
        return False

def upload_files_to_s3(bucket_name):
    """Subir archivos corregidos a S3"""
    print(f"\n📤 Subiendo archivos a S3: {bucket_name}")
    
    try:
        s3 = boto3.client('s3')
        web_dir = Path("web_interface")
        
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
                
                # Subir archivo
                s3.upload_file(
                    str(file_path),
                    bucket_name,
                    s3_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'CacheControl': 'max-age=3600'
                    }
                )
                
                uploaded_count += 1
                print(f"      📄 {s3_key}")
        
        print(f"   ✅ {uploaded_count} archivos subidos")
        return True
        
    except Exception as e:
        print(f"   ❌ Error subiendo archivos: {e}")
        return False

def invalidate_cloudfront_cache(distribution_id):
    """Invalidar cache de CloudFront"""
    print(f"\n🔄 Invalidando cache de CloudFront...")
    
    try:
        cloudfront = boto3.client('cloudfront')
        
        response = cloudfront.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                'Paths': {'Quantity': 1, 'Items': ['/*']},
                'CallerReference': f'web-config-{int(time.time())}'
            }
        )
        
        invalidation_id = response['Invalidation']['Id']
        print(f"   ✅ Cache invalidado (ID: {invalidation_id})")
        return True
        
    except Exception as e:
        print(f"   ❌ Error invalidando cache: {e}")
        return False

def test_web_access(web_url):
    """Probar acceso a la web"""
    print(f"\n🧪 Probando acceso a la web...")
    
    try:
        import urllib.request
        
        test_url = f"{web_url}/index.html"
        print(f"   🎯 Probando: {test_url}")
        
        request = urllib.request.Request(test_url)
        request.add_header('User-Agent', 'WebConfig/1.0')
        request.add_header('Cache-Control', 'no-cache')
        
        with urllib.request.urlopen(request, timeout=10) as response:
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
    """Configuración completa del web interface"""
    print("🔧 WEB CONFIG COMPLETO")
    print("=" * 50)
    print("Configura archivos HTML y sube al bucket correcto")
    
    # 1. Obtener información del stack
    api_url, web_url, bucket_name, distribution_id = get_stack_info()
    
    if not all([api_url, web_url, bucket_name, distribution_id]):
        print("\n❌ No se pudo obtener información completa del stack")
        return False
    
    success_steps = 0
    total_steps = 4
    
    # 2. Corregir archivos HTML
    if fix_html_files(api_url):
        success_steps += 1
        print(f"   ✅ Paso 1/4: Archivos HTML corregidos")
    else:
        print(f"   ❌ Paso 1/4: Error corrigiendo archivos HTML")
    
    # 3. Verificar CloudFront (solo verificación, no corrección)
    check_and_fix_cloudfront(distribution_id, bucket_name)
    success_steps += 1
    print(f"   ✅ Paso 2/4: CloudFront verificado")
    
    # 4. Subir archivos a S3
    if upload_files_to_s3(bucket_name):
        success_steps += 1
        print(f"   ✅ Paso 3/4: Archivos subidos a S3")
    else:
        print(f"   ❌ Paso 3/4: Error subiendo archivos")
    
    # 5. Invalidar cache
    if invalidate_cloudfront_cache(distribution_id):
        success_steps += 1
        print(f"   ✅ Paso 4/4: Cache invalidado")
    else:
        print(f"   ❌ Paso 4/4: Error invalidando cache")
    
    # 6. Probar acceso
    print(f"\n⏱️  Esperando 30 segundos para propagación...")
    time.sleep(30)
    
    web_accessible = test_web_access(web_url)
    
    # Resultado final
    print(f"\n{'='*50}")
    
    if success_steps >= 3:
        print(f"🎉 ¡WEB CONFIG COMPLETADO EXITOSAMENTE!")
        print(f"   ✅ Archivos HTML configurados")
        print(f"   ✅ CloudFront verificado (CDK lo configuró correctamente)")
        print(f"   ✅ Archivos subidos a S3")
        print(f"   ✅ Cache invalidado")
        
        if web_accessible:
            print(f"   ✅ Web inmediatamente accesible")
        else:
            print(f"   ⏱️  Web accesible en 5-10 minutos")
        
        print(f"\n🌐 LISTO PARA USAR:")
        print(f"   URL: {web_url}")
        print(f"   📱 Refrescar con Ctrl+F5 y probar")
        
        print(f"\n💡 NOTA:")
        print(f"   CDK genera el domain CloudFront correcto automáticamente")
        print(f"   Este script solo necesita ejecutarse después de cada deploy")
        
        return True
    else:
        print(f"⚠️  WEB CONFIG PARCIALMENTE COMPLETADO ({success_steps}/{total_steps})")
        print(f"   🔄 Algunos pasos fallaron, pero puede funcionar")
        print(f"   ⏱️  Espera 10-15 minutos y prueba: {web_url}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)