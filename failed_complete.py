#!/usr/bin/env python3
"""
🔬 DIAGNÓSTICO PROFUNDO "Failed to fetch"
Identifica exactamente qué está fallando cuando el usuario ve el error
"""

import boto3
import json
import urllib.request
import urllib.error
import time
import base64
from datetime import datetime

def get_stack_info():
    """Obtener información del stack"""
    cf = boto3.client('cloudformation')
    response = cf.describe_stacks(StackName='RekognitionPocStack')
    
    outputs = {}
    for output in response['Stacks'][0]['Outputs']:
        outputs[output['OutputKey']] = output['OutputValue']
    
    return outputs

def test_exact_user_flow():
    """Probar exactamente el flujo que hace el usuario en la web"""
    print("🎯 PROBANDO FLUJO EXACTO DEL USUARIO")
    print("=" * 50)
    
    outputs = get_stack_info()
    api_url = outputs['APIGatewayURL'].rstrip('/')
    
    print(f"API Base: {api_url}")
    
    # PASO 1: Simular /users/lookup (lo que hace index.html)
    print(f"\n📋 PASO 1: Probando /users/lookup")
    
    lookup_data = {
        "user_data": {
            "document_type": "DNI",
            "document_number": "12345678",
            "phone_number": "123456789"
        }
    }
    
    try:
        request = urllib.request.Request(
            f"{api_url}/users/lookup",
            data=json.dumps(lookup_data).encode('utf-8'),
            method='POST'
        )
        request.add_header('Content-Type', 'application/json')
        request.add_header('Origin', 'https://d1710jdcfp5apu.cloudfront.net')
        
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"   ✅ /users/lookup: {response.status}")
            print(f"   📄 Respuesta: {json.dumps(result, indent=2)}")
            lookup_success = True
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"   ❌ /users/lookup HTTP Error: {e.code}")
        print(f"   📄 Error body: {error_body}")
        lookup_success = False
        
    except Exception as e:
        print(f"   ❌ /users/lookup Error: {e}")
        lookup_success = False
    
    # PASO 2: Simular /documents/index (para usuarios nuevos)
    print(f"\n📋 PASO 2: Probando /documents/index")
    
    # Crear una imagen falsa en base64
    fake_image = create_fake_image_base64()
    
    index_data = {
        "user_data": {
            "document_type": "DNI",
            "document_number": "12345678",
            "phone_number": "123456789"
        },
        "document_image": fake_image
    }
    
    try:
        request = urllib.request.Request(
            f"{api_url}/documents/index",
            data=json.dumps(index_data).encode('utf-8'),
            method='POST'
        )
        request.add_header('Content-Type', 'application/json')
        request.add_header('Origin', 'https://d1710jdcfp5apu.cloudfront.net')
        
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"   ✅ /documents/index: {response.status}")
            print(f"   📄 Respuesta: {json.dumps(result, indent=2)}")
            index_success = True
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"   ❌ /documents/index HTTP Error: {e.code}")
        print(f"   📄 Error body: {error_body}")
        index_success = False
        
    except Exception as e:
        print(f"   ❌ /documents/index Error: {e}")
        index_success = False
    
    # PASO 3: Simular /users/validate (validación facial)
    print(f"\n📋 PASO 3: Probando /users/validate")
    
    validate_data = {
        "liveness_image": fake_image,
        "user_context": {
            "userData": {
                "document_type": "DNI",
                "document_number": "12345678",
                "phone_number": "123456789"
            },
            "result": {"user_exists": False}
        }
    }
    
    try:
        request = urllib.request.Request(
            f"{api_url}/users/validate",
            data=json.dumps(validate_data).encode('utf-8'),
            method='POST'
        )
        request.add_header('Content-Type', 'application/json')
        request.add_header('Origin', 'https://d1710jdcfp5apu.cloudfront.net')
        
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"   ✅ /users/validate: {response.status}")
            print(f"   📄 Respuesta: {json.dumps(result, indent=2)}")
            validate_success = True
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"   ❌ /users/validate HTTP Error: {e.code}")
        print(f"   📄 Error body: {error_body}")
        validate_success = False
        
    except Exception as e:
        print(f"   ❌ /users/validate Error: {e}")
        validate_success = False
    
    return lookup_success, index_success, validate_success

def create_fake_image_base64():
    """Crear una imagen falsa en base64 para pruebas"""
    # Una imagen PNG 1x1 pixel transparente en base64
    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

def check_lambda_functions():
    """Verificar estado de las funciones Lambda"""
    print(f"\n🔍 VERIFICANDO FUNCIONES LAMBDA")
    print("=" * 40)
    
    lambda_client = boto3.client('lambda')
    
    functions = [
        'rekognition-poc-user-validator',
        'rekognition-poc-document-indexer'
    ]
    
    for func_name in functions:
        try:
            response = lambda_client.get_function(FunctionName=func_name)
            config = response['Configuration']
            
            print(f"\n📋 {func_name}:")
            print(f"   Estado: {config['State']}")
            print(f"   Runtime: {config['Runtime']}")
            print(f"   Timeout: {config['Timeout']}s")
            print(f"   Memory: {config['MemorySize']}MB")
            print(f"   Última modificación: {config['LastModified']}")
            
            # Verificar variables de entorno
            env_vars = config.get('Environment', {}).get('Variables', {})
            print(f"   Variables de entorno:")
            for key, value in env_vars.items():
                print(f"      {key}: {value}")
                
        except Exception as e:
            print(f"   ❌ Error obteniendo {func_name}: {e}")

def check_recent_lambda_logs():
    """Verificar logs recientes de Lambda"""
    print(f"\n📋 VERIFICANDO LOGS RECIENTES DE LAMBDA")
    print("=" * 50)
    
    logs_client = boto3.client('logs')
    
    # Obtener logs de los últimos 30 minutos
    end_time = int(time.time() * 1000)
    start_time = end_time - (30 * 60 * 1000)  # 30 minutos atrás
    
    log_groups = [
        '/aws/lambda/rekognition-poc-user-validator',
        '/aws/lambda/rekognition-poc-document-indexer'
    ]
    
    for log_group in log_groups:
        try:
            print(f"\n📋 {log_group}:")
            
            # Obtener streams recientes
            streams_response = logs_client.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=3
            )
            
            for stream in streams_response['logStreams']:
                stream_name = stream['logStreamName']
                
                try:
                    # Obtener eventos del stream
                    events_response = logs_client.get_log_events(
                        logGroupName=log_group,
                        logStreamName=stream_name,
                        startTime=start_time,
                        endTime=end_time
                    )
                    
                    events = events_response['events']
                    if events:
                        print(f"   📄 Stream: {stream_name}")
                        print(f"      Eventos recientes: {len(events)}")
                        
                        # Mostrar últimos 3 eventos
                        for event in events[-3:]:
                            timestamp = datetime.fromtimestamp(event['timestamp']/1000)
                            message = event['message'].strip()
                            print(f"      [{timestamp}] {message}")
                            
                except Exception as e:
                    print(f"      ❌ Error obteniendo eventos: {e}")
                    
        except Exception as e:
            print(f"   ❌ Error obteniendo logs de {log_group}: {e}")

def check_api_gateway_config():
    """Verificar configuración de API Gateway"""
    print(f"\n🌐 VERIFICANDO CONFIGURACIÓN DE API GATEWAY")
    print("=" * 50)
    
    try:
        # Obtener API Gateway ID del stack
        outputs = get_stack_info()
        api_url = outputs['APIGatewayURL']
        
        # Extraer API ID de la URL
        api_id = api_url.split('//')[1].split('.')[0]
        
        print(f"API ID: {api_id}")
        
        apigw_client = boto3.client('apigateway')
        
        # Obtener información de la API
        api_info = apigw_client.get_rest_api(restApiId=api_id)
        print(f"API Name: {api_info['name']}")
        print(f"API Description: {api_info.get('description', 'N/A')}")
        
        # Obtener recursos
        resources = apigw_client.get_resources(restApiId=api_id)
        
        print(f"\n📋 RECURSOS Y MÉTODOS:")
        for resource in resources['items']:
            path = resource['path']
            print(f"   📂 {path}")
            
            if 'resourceMethods' in resource:
                for method in resource['resourceMethods']:
                    print(f"      🔗 {method}")
                    
                    # Verificar CORS para métodos OPTIONS
                    if method == 'OPTIONS':
                        try:
                            method_info = apigw_client.get_method(
                                restApiId=api_id,
                                resourceId=resource['id'],
                                httpMethod='OPTIONS'
                            )
                            print(f"         ✅ CORS configurado")
                        except:
                            print(f"         ❌ CORS no encontrado")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verificando API Gateway: {e}")
        return False

def main():
    """Diagnóstico completo y profundo"""
    print("🔬 DIAGNÓSTICO PROFUNDO 'Failed to fetch'")
    print("=" * 60)
    print("Identificando exactamente qué está fallando")
    
    try:
        # 1. Verificar funciones Lambda
        check_lambda_functions()
        
        # 2. Verificar logs recientes
        check_recent_lambda_logs()
        
        # 3. Verificar API Gateway
        check_api_gateway_config()
        
        # 4. Probar flujo exacto del usuario
        lookup_ok, index_ok, validate_ok = test_exact_user_flow()
        
        # 5. Diagnóstico final
        print(f"\n{'='*60}")
        print("🎯 DIAGNÓSTICO FINAL")
        
        print(f"\n📊 RESULTADOS DE PRUEBAS:")
        print(f"   /users/lookup: {'✅' if lookup_ok else '❌'}")
        print(f"   /documents/index: {'✅' if index_ok else '❌'}")
        print(f"   /users/validate: {'✅' if validate_ok else '❌'}")
        
        if not lookup_ok:
            print(f"\n🔍 PROBLEMA IDENTIFICADO: /users/lookup está fallando")
            print(f"   💡 Solución: Verificar función rekognition-poc-user-validator")
            
        elif not index_ok:
            print(f"\n🔍 PROBLEMA IDENTIFICADO: /documents/index está fallando")
            print(f"   💡 Solución: Verificar función rekognition-poc-document-indexer")
            
        elif not validate_ok:
            print(f"\n🔍 PROBLEMA IDENTIFICADO: /users/validate está fallando")
            print(f"   💡 Solución: Verificar validación facial y Rekognition")
            
        else:
            print(f"\n🤔 PROBLEMA MISTERIOSO: Todas las APIs funcionan desde Python")
            print(f"   💡 Posibles causas:")
            print(f"      1. Problema específico del navegador")
            print(f"      2. Headers faltantes en el frontend")
            print(f"      3. Tamaño de payload demasiado grande")
            print(f"      4. Timeout en el frontend")
            
        print(f"\n🔧 PRÓXIMOS PASOS:")
        print(f"   1. Revisar logs de Lambda arriba")
        print(f"   2. Abrir DevTools del navegador (F12)")
        print(f"   3. En Network tab, ver exactamente qué request está fallando")
        print(f"   4. Copiar el error exacto del navegador")
        
        return not (lookup_ok and index_ok and validate_ok)
        
    except Exception as e:
        print(f"❌ Error en diagnóstico: {e}")
        return False

if __name__ == "__main__":
    main()