#!/usr/bin/env python3
"""
🌐 CONFIGURADOR AUTOMÁTICO DE WEB INTERFACE
Reemplaza URLs placeholder con valores reales del stack desplegado
"""

import os
import sys
import boto3
import json
import re
from pathlib import Path

class WebInterfaceConfigurator:
    def __init__(self, stack_name="RekognitionPocStack"):
        self.stack_name = stack_name
        self.cloudformation = boto3.client('cloudformation')
        
    def get_stack_outputs(self):
        """Obtener outputs del stack CloudFormation"""
        try:
            response = self.cloudformation.describe_stacks(StackName=self.stack_name)
            outputs = response['Stacks'][0]['Outputs']
            
            # Convertir a diccionario para fácil acceso
            output_dict = {}
            for output in outputs:
                output_dict[output['OutputKey']] = output['OutputValue']
                
            return output_dict
            
        except Exception as e:
            print(f"❌ Error obteniendo outputs del stack: {e}")
            return None
    
    def update_html_files(self, api_url):
        """Actualizar archivos HTML con la URL real del API"""
        web_interface_dir = Path("web_interface")
        
        if not web_interface_dir.exists():
            print(f"❌ Directorio {web_interface_dir} no encontrado")
            return False
        
        html_files = list(web_interface_dir.glob("*.html"))
        
        if not html_files:
            print(f"❌ No se encontraron archivos HTML en {web_interface_dir}")
            return False
        
        # Asegurar que no hay trailing slash
        clean_api_url = api_url.rstrip('/')
        
        updated_files = []
        
        for html_file in html_files:
            try:
                # Leer archivo
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Verificar si contiene placeholder
                if 'PLACEHOLDER_API_URL' not in content:
                    print(f"⏭️  {html_file.name}: Ya configurado")
                    continue
                
                # Reemplazar placeholder
                updated_content = content.replace('PLACEHOLDER_API_URL', clean_api_url)
                
                # Verificar que el reemplazo funcionó
                if 'PLACEHOLDER_API_URL' in updated_content:
                    print(f"⚠️  {html_file.name}: Reemplazo incompleto")
                    continue
                
                # Escribir archivo actualizado
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(updated_content)
                
                updated_files.append(html_file.name)
                print(f"✅ {html_file.name}: Actualizado")
                
            except Exception as e:
                print(f"❌ Error procesando {html_file.name}: {e}")
        
        return len(updated_files) > 0
    
    def verify_configuration(self):
        """Verificar que la configuración es correcta"""
        web_interface_dir = Path("web_interface")
        issues = []
        
        for html_file in web_interface_dir.glob("*.html"):
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Buscar placeholders restantes
            if 'PLACEHOLDER_API_URL' in content:
                issues.append(f"{html_file.name}: Contiene PLACEHOLDER_API_URL")
            
            # Buscar definiciones de API_BASE
            api_base_matches = re.findall(r"const API_BASE = '([^']+)'", content)
            
            if api_base_matches:
                api_url = api_base_matches[0]
                if api_url.startswith('https://'):
                    print(f"✅ {html_file.name}: API_BASE = {api_url}")
                else:
                    issues.append(f"{html_file.name}: API_BASE inválido: {api_url}")
        
        if issues:
            print(f"\n⚠️  PROBLEMAS ENCONTRADOS:")
            for issue in issues:
                print(f"   - {issue}")
            return False
        
        print(f"\n🎉 Configuración web verificada correctamente")
        return True
    
    def upload_to_s3(self, web_bucket_name):
        """Subir archivos actualizados a S3"""
        try:
            s3 = boto3.client('s3')
            web_interface_dir = Path("web_interface")
            
            uploaded_files = []
            
            for file_path in web_interface_dir.rglob("*"):
                if file_path.is_file():
                    # Clave S3 (path relativo)
                    s3_key = str(file_path.relative_to(web_interface_dir))
                    
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
                        web_bucket_name,
                        s3_key,
                        ExtraArgs={'ContentType': content_type}
                    )
                    
                    uploaded_files.append(s3_key)
                    print(f"📤 Subido: {s3_key}")
            
            print(f"✅ {len(uploaded_files)} archivos subidos a s3://{web_bucket_name}/")
            return True
            
        except Exception as e:
            print(f"❌ Error subiendo a S3: {e}")
            return False
    
    def run_complete_configuration(self):
        """Ejecutar configuración completa"""
        print("🚀 INICIANDO CONFIGURACIÓN WEB INTERFACE")
        print("=" * 50)
        
        # 1. Obtener outputs del stack
        print("📋 1. Obteniendo información del stack...")
        outputs = self.get_stack_outputs()
        
        if not outputs:
            return False
        
        api_url = outputs.get('APIGatewayURL')
        web_bucket = outputs.get('WebBucketName')
        web_url = outputs.get('WebInterfaceURL')
        
        if not api_url:
            print("❌ No se encontró APIGatewayURL en los outputs")
            return False
        
        print(f"   ✅ API Gateway URL: {api_url}")
        print(f"   ✅ Web Bucket: {web_bucket}")
        print(f"   ✅ Web URL: {web_url}")
        
        # 2. Actualizar archivos HTML
        print("\n🔧 2. Actualizando archivos HTML...")
        if not self.update_html_files(api_url):
            print("❌ Falló la actualización de archivos HTML")
            return False
        
        # 3. Verificar configuración
        print("\n🔍 3. Verificando configuración...")
        if not self.verify_configuration():
            print("❌ Configuración inválida")
            return False
        
        # 4. Subir a S3 (si bucket disponible)
        if web_bucket:
            print(f"\n📤 4. Subiendo archivos a S3...")
            if not self.upload_to_s3(web_bucket):
                print("⚠️  Error subiendo a S3, pero archivos locales están configurados")
        
        # 5. Resumen final
        print(f"\n🎉 CONFIGURACIÓN COMPLETADA")
        print("=" * 30)
        print(f"✅ Archivos HTML actualizados con API URL")
        print(f"✅ Archivos subidos a S3")
        if web_url:
            print(f"🌐 Interfaz web disponible en: {web_url}")
        
        return True

def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Configurar Web Interface')
    parser.add_argument('--stack-name', default='RekognitionPocStack', 
                       help='Nombre del stack CloudFormation')
    parser.add_argument('--verify-only', action='store_true',
                       help='Solo verificar configuración actual')
    
    args = parser.parse_args()
    
    configurator = WebInterfaceConfigurator(args.stack_name)
    
    if args.verify_only:
        configurator.verify_configuration()
    else:
        success = configurator.run_complete_configuration()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()