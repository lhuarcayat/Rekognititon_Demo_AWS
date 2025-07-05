#!/usr/bin/env python3
"""
⚡ SOLUCIONADOR RÁPIDO "Failed to fetch"
Diagnóstica y corrige automáticamente el error en un solo comando
"""

import boto3
import json
import subprocess
import time
import urllib.request
from pathlib import Path

def quick_diagnose():
    """Diagnóstico rápido del problema"""
    print("🔍 DIAGNÓSTICO RÁPIDO...")
    
    issues = []
    
    # 1. Verificar stack
    try:
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        stack_status = response['Stacks'][0]['StackStatus']
        
        if 'COMPLETE' not in stack_status:
            issues.append('Stack no está en estado saludable')
        else:
            print("   ✅ Stack OK")
    except Exception as e:
        issues.append(f'Stack no accesible: {str(e)[:50]}')
    
    # 2. Verificar configuración web
    try:
        web_dir = Path("web_interface")
        if web_dir.exists():
            for html_file in web_dir.glob("*.html"):
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'PLACEHOLDER_API_URL' in content:
                    issues.append('Archivos web contienen PLACEHOLDER')
                    break
            else:
                print("   ✅ Archivos web OK")
        else:
            issues.append('Directorio web_interface no encontrado')
    except Exception as e:
        issues.append(f'Error verificando archivos web: {str(e)[:50]}')
    
    # 3. Test rápido API
    try:
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        outputs = {out['OutputKey']: out['OutputValue'] for out in response['Stacks'][0]['Outputs']}
        api_url = outputs.get('APIGatewayURL', '').rstrip('/')
        
        if api_url:
            # Test CORS básico
            request = urllib.request.Request(f"{api_url}/users/lookup", method='OPTIONS')
            request.add_header('Origin', 'https://example.com')
            
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    if response.status == 200:
                        print("   ✅ API accesible")
                    else:
                        issues.append(f'API responde {response.status}')
            except Exception:
                issues.append('API no responde a CORS')
        else:
            issues.append('API URL no encontrada')
    except Exception as e:
        issues.append(f'Error probando API: {str(e)[:50]}')
    
    return issues

def apply_quick_fixes():
    """Aplicar correcciones rápidas"""
    print(f"\n🔧 APLICANDO CORRECCIONES RÁPIDAS...")
    
    fixes_applied = []
    
    # 1. Configurar archivos web
    try:
        print("   📤 Configurando archivos web...")
        result = subprocess.run(
            ['python', 'scripts/web_config.py'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            fixes_applied.append('Web config actualizado')
            print("      ✅ Archivos web configurados")
        else:
            print(f"      ⚠️  Web config tuvo problemas: {result.stderr[:100]}")
    except Exception as e:
        print(f"      ❌ Error configurando web: {e}")
    
    # 2. Corregir CORS si es necesario
    try:
        print("   🌐 Verificando y corrigiendo CORS...")
        
        # Verificar CORS rápidamente
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        outputs = {out['OutputKey']: out['OutputValue'] for out in response['Stacks'][0]['Outputs']}
        api_url = outputs.get('APIGatewayURL', '').rstrip('/')
        
        if api_url:
            request = urllib.request.Request(f"{api_url}/users/lookup", method='OPTIONS')
            request.add_header('Origin', 'https://example.com')
            
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    headers = dict(response.headers)
                    if 'Access-Control-Allow-Origin' in headers:
                        print("      ✅ CORS ya configurado")
                    else:
                        raise Exception("CORS headers missing")
            except Exception:
                print("      🔧 Corrigiendo CORS...")
                cors_result = subprocess.run(
                    ['python', 'scripts/fix_cors_issues.py'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if cors_result.returncode == 0:
                    fixes_applied.append('CORS corregido')
                    print("      ✅ CORS corregido")
                else:
                    print(f"      ⚠️  CORS tuvo problemas")
    except Exception as e:
        print(f"      ❌ Error con CORS: {e}")
    
    # 3. Invalidar cache CloudFront
    try:
        print("   🔄 Invalidando cache CloudFront...")
        
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        outputs = {out['OutputKey']: out['OutputValue'] for out in response['Stacks'][0]['Outputs']}
        distribution_id = outputs.get('CloudFrontDistributionId')
        
        if distribution_id:
            cloudfront = boto3.client('cloudfront')
            cloudfront.create_invalidation(
                DistributionId=distribution_id,
                InvalidationBatch={
                    'Paths': {'Quantity': 1, 'Items': ['/*']},
                    'CallerReference': f'quickfix-{int(time.time())}'
                }
            )
            fixes_applied.append('Cache invalidado')
            print("      ✅ Cache invalidado")
        else:
            print("      ⚠️  Distribution ID no encontrado")
    except Exception as e:
        print(f"      ❌ Error invalidando cache: {e}")
    
    return fixes_applied

def test_fix():
    """Probar si la corrección funcionó"""
    print(f"\n🧪 PROBANDO CORRECCIÓN...")
    
    try:
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName='RekognitionPocStack')
        outputs = {out['OutputKey']: out['OutputValue'] for out in response['Stacks'][0]['Outputs']}
        api_url = outputs.get('APIGatewayURL', '').rstrip('/')
        web_url = outputs.get('WebInterfaceURL')
        
        if not api_url:
            print("   ❌ API URL no disponible")
            return False
        
        # Test 1: CORS en API
        print("   🌐 Probando CORS...")
        request = urllib.request.Request(f"{api_url}/users/lookup", method='OPTIONS')
        request.add_header('Origin', 'https://example.com')
        
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                headers = dict(response.headers)
                if 'Access-Control-Allow-Origin' in headers:
                    print("      ✅ CORS funciona")
                    cors_ok = True
                else:
                    print("      ❌ CORS falta headers")
                    cors_ok = False
        except Exception as e:
            print(f"      ❌ CORS error: {e}")
            cors_ok = False
        
        # Test 2: API funcional
        print("   📡 Probando API...")
        test_data = json.dumps({
            'user_data': {
                'document_type': 'DNI',
                'document_number': '12345678',
                'phone_number': '123456789'
            }
        }).encode('utf-8')
        
        api_request = urllib.request.Request(f"{api_url}/users/lookup", data=test_data, method='POST')
        api_request.add_header('Content-Type', 'application/json')
        api_request.add_header('Origin', 'https://example.com')
        
        try:
            with urllib.request.urlopen(api_request, timeout=10) as response:
                print(f"      ✅ API responde: {response.status}")
                api_ok = True
        except urllib.error.HTTPError as e:
            if e.code in [400, 403, 500]:  # Errores esperados con datos de prueba
                print(f"      ✅ API accesible (error esperado: {e.code})")
                api_ok = True
            else:
                print(f"      ❌ API error: {e.code}")
                api_ok = False
        except Exception as e:
            print(f"      ❌ API error: {e}")
            api_ok = False
        
        # Test 3: Web accesible
        print("   🌐 Probando web...")
        if web_url:
            try:
                web_request = urllib.request.Request(f"{web_url}/index.html")
                with urllib.request.urlopen(web_request, timeout=10) as response:
                    if response.status == 200:
                        print("      ✅ Web accesible")
                        web_ok = True
                    else:
                        print(f"      ⚠️  Web status: {response.status}")
                        web_ok = False
            except Exception as e:
                print(f"      ⚠️  Web error (puede ser normal): {e}")
                web_ok = False
        else:
            print("      ❌ Web URL no disponible")
            web_ok = False
        
        # Resultado final
        success = cors_ok and api_ok
        
        if success:
            print(f"\n   🎉 ¡CORRECCIÓN EXITOSA!")
            print(f"      ✅ API funcional con CORS")
            if web_ok:
                print(f"      ✅ Web accesible")
            print(f"      🌐 Probar en: {web_url}")
        else:
            print(f"\n   ⚠️  CORRECCIÓN PARCIAL")
            print(f"      CORS: {'✅' if cors_ok else '❌'}")
            print(f"      API: {'✅' if api_ok else '❌'}")
            print(f"      Web: {'✅' if web_ok else '⚠️'}")
        
        return success
        
    except Exception as e:
        print(f"   ❌ Error en test: {e}")
        return False

def main():
    """Corrección completa del error Failed to fetch"""
    print("⚡ SOLUCIONADOR RÁPIDO 'Failed to fetch'")
    print("=" * 60)
    print("Diagnóstica y corrige automáticamente problemas de API")
    
    # 1. Diagnóstico rápido
    issues = quick_diagnose()
    
    if not issues:
        print(f"\n✅ No se detectaron problemas obvios")
        print(f"💡 El error puede ser temporal o de conectividad")
    else:
        print(f"\n❌ Problemas detectados:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    
    # 2. Aplicar correcciones
    fixes = apply_quick_fixes()
    
    if fixes:
        print(f"\n🔧 Correcciones aplicadas:")
        for fix in fixes:
            print(f"   ✅ {fix}")
        
        # Esperar un poco para propagación
        print(f"\n⏱️  Esperando 30 segundos para propagación...")
        time.sleep(30)
    else:
        print(f"\n⚠️  No se aplicaron correcciones automáticas")
    
    # 3. Probar corrección
    success = test_fix()
    
    # 4. Instrucciones finales
    print(f"\n📋 PRÓXIMOS PASOS:")
    
    if success:
        print(f"   1. 🌐 Refrescar la página web (Ctrl+F5)")
        print(f"   2. 📱 Probar el flujo de validación")
        print(f"   3. 🎉 ¡Debería funcionar ahora!")
    else:
        print(f"   1. ⏱️  Esperar 5-10 minutos más")
        print(f"   2. 🔄 Probar nuevamente la web")
        print(f"   3. 📋 Si persiste:")
        print(f"      - python scripts/diagnose_api_error.py")
        print(f"      - python scripts/check_lambda_logs.py")
        print(f"      - cdk deploy RekognitionPocStack")
    
    print(f"\n💡 CONSEJO:")
    print(f"   Si ves 'Failed to fetch', usa Ctrl+F5 para refrescar")
    print(f"   Los cambios de API pueden tardar unos minutos")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)