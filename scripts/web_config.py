#!/usr/bin/env python3
"""
🔧 CORRECTOR ESPECÍFICO DE WEB CONFIG
Completa la corrección que tuvo problemas en el script anterior
"""

import boto3
import json
import re
from pathlib import Path

def get_api_url():
    """Obtener URL del API desde CloudFormation"""
    print("📋 Obteniendo URL del API...")
    
    try:
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        
        outputs = {}
        for output in response['Stacks'][0]['Outputs']:
            outputs[output['OutputKey']] = output['OutputValue']
        
        api_url = outputs.get('APIGatewayURL', '').rstrip('/')
        web_url = outputs.get('WebInterfaceURL')
        bucket_name = outputs.get('WebBucketName')
        
        print(f"   ✅ API URL: {api_url}")
        print(f"   ✅ Web URL: {web_url}")
        print(f"   ✅ Bucket: {bucket_name}")
        
        return api_url, web_url, bucket_name
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None, None, None

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

def upload_fixed_files(bucket_name):
    """Subir archivos corregidos a S3"""
    print(f"\n📤 Subiendo archivos corregidos a S3...")
    
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

def verify_web_files(bucket_name):
    """Verificar archivos en S3"""
    print(f"\n🔍 Verificando archivos en S3...")
    
    try:
        s3 = boto3.client('s3')
        response = s3.list_objects_v2(Bucket=bucket_name)
        
        if 'Contents' not in response:
            print(f"   ❌ Bucket está vacío")
            return False
        
        files = [obj['Key'] for obj in response['Contents']]
        
        print(f"   📁 Archivos en S3: {len(files)}")
        for file in files:
            print(f"      📄 {file}")
        
        # Verificar archivos críticos
        critical_files = ['index.html', 'capture.html', 'transaction.html']
        missing_files = [f for f in critical_files if f not in files]
        
        if missing_files:
            print(f"   ❌ Archivos críticos faltantes: {missing_files}")
            return False
        else:
            print(f"   ✅ Todos los archivos críticos presentes")
            return True
            
    except Exception as e:
        print(f"   ❌ Error verificando archivos: {e}")
        return False

def test_web_access(web_url):
    """Probar acceso a la web"""
    print(f"\n🧪 Probando acceso a la web...")
    
    try:
        import urllib.request
        
        test_url = f"{web_url}/index.html"
        print(f"   🎯 Probando: {test_url}")
        
        request = urllib.request.Request(test_url)
        request.add_header('User-Agent', 'WebConfigFix/1.0')
        
        with urllib.request.urlopen(request, timeout=10) as response:
            content = response.read().decode('utf-8')
            
            # Verificar que no tenga PLACEHOLDER
            if 'PLACEHOLDER_API_URL' in content:
                print(f"      ❌ Aún contiene PLACEHOLDER_API_URL")
                return False
            
            # Verificar que tenga API_BASE correcto
            import re
            api_base_match = re.search(r"const API_BASE = '([^']+)'", content)
            if api_base_match:
                api_base = api_base_match.group(1)
                print(f"      ✅ API_BASE configurado: {api_base}")
                if api_base.startswith('https://') and 'amazonaws.com' in api_base:
                    print(f"      ✅ URL del API válida")
                    return True
                else:
                    print(f"      ❌ URL del API inválida")
                    return False
            else:
                print(f"      ❌ API_BASE no encontrado")
                return False
                
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    """Corrección específica del web config"""
    print("🔧 CORRECTOR ESPECÍFICO DE WEB CONFIG")
    print("=" * 50)
    print("Completa la corrección que tuvo problemas")
    
    # 1. Obtener URLs
    api_url, web_url, bucket_name = get_api_url()
    
    if not all([api_url, web_url, bucket_name]):
        print("\n❌ No se pudo obtener información del stack")
        return False
    
    # 2. Corregir archivos HTML localmente
    if not fix_html_files(api_url):
        print("\n❌ Error corrigiendo archivos HTML")
        return False
    
    # 3. Subir archivos corregidos
    if not upload_fixed_files(bucket_name):
        print("\n❌ Error subiendo archivos")
        return False
    
    # 4. Verificar archivos en S3
    if not verify_web_files(bucket_name):
        print("\n❌ Error verificando archivos")
        return False
    
    # 5. Probar acceso web
    if test_web_access(web_url):
        print(f"\n🎉 ¡WEB CONFIG CORREGIDO COMPLETAMENTE!")
        print(f"   ✅ Archivos HTML actualizados")
        print(f"   ✅ API URL configurada correctamente")
        print(f"   ✅ Archivos subidos a S3")
        print(f"   ✅ Web accesible y funcional")
        
        print(f"\n🌐 LISTO PARA USAR:")
        print(f"   URL: {web_url}")
        print(f"   📱 Refrescar con Ctrl+F5 y probar")
        
        return True
    else:
        print(f"\n⚠️  WEB CONFIG PARCIALMENTE CORREGIDO")
        print(f"   🔄 Los archivos están subidos pero pueden tardar unos minutos")
        print(f"   💡 Espera 5-10 minutos y prueba: {web_url}")
        
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)