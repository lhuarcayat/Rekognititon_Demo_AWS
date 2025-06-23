
import boto3
import json

def execute_smart_index_all():
    """
    MODO 1: Ejecutar Smart Index All
    """
    print("🔄 EJECUTANDO: Smart Index All")
    print("Descripción: Indexa todos los documentos, saltando duplicados")
    print("=" * 60)
    
    lambda_client = boto3.client('lambda')
    function_name = 'rekognition-poc-document-indexer'
    
    # 🎯 PAYLOAD PARA SMART INDEX ALL
    payload = {
        "action": "smart_index_all"
    }
    
    print(f"📋 Payload: {json.dumps(payload, indent=2)}")
    print(f"🚀 Invocando lambda...")
    
    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',  # Síncrono
            Payload=json.dumps(payload)
        )
        
        # Leer respuesta
        result = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            print(f"✅ ÉXITO - StatusCode: {response['StatusCode']}")
            
            # Parsear body
            if 'body' in result:
                body = json.loads(result['body'])
                
                print(f"\n📊 RESULTADOS:")
                print(f"   💬 Mensaje: {body.get('message', 'N/A')}")
                print(f"   🆕 Nuevos indexados: {body.get('new_indexed', 0)}")
                print(f"   ⏭️  Saltados (duplicados): {body.get('skipped', 0)}")
                print(f"   ❌ Errores: {body.get('errors', 0)}")
                
                # Mostrar detalles si hay pocos documentos
                if 'results' in body and len(body['results']) <= 10:
                    print(f"\n📄 DETALLES POR DOCUMENTO:")
                    for i, res in enumerate(body['results'], 1):
                        doc = res.get('document', 'Unknown')
                        status = res.get('status', 'Unknown')
                        
                        if status == 'SKIPPED_DUPLICATE':
                            icon = "⏭️"
                        elif res.get('success'):
                            icon = "🆕"
                        else:
                            icon = "❌"
                            
                        print(f"      {i}. {icon} {doc}")
                        if 'person_name' in res:
                            print(f"         👤 {res['person_name']}")
                        if 'error' in res:
                            print(f"         🚫 {res['error']}")
                            
                return body
                
        else:
            print(f"❌ FALLÓ - StatusCode: {response['StatusCode']}")
            print(f"📋 Error: {result}")
            return None
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return None

if __name__ == "__main__":
    execute_smart_index_all()