import boto3
import json

def execute_index_new_only():
    """
    MODO 2: Ejecutar Index New Only
    """
    print("🆕 EJECUTANDO: Index New Only")
    print("Descripción: Solo indexa documentos completamente nuevos")
    print("=" * 60)
    
    lambda_client = boto3.client('lambda')
    function_name = 'rekognition-poc-document-indexer'
    
    # 🎯 PAYLOAD PARA INDEX NEW ONLY
    payload = {
        "action": "index_new_only"
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
                print(f"   📊 Total nuevos encontrados: {body.get('total_new_found', 0)}")
                print(f"   💾 Documentos ya existentes: {body.get('total_existing', 0)}")
                print(f"   ❌ Errores: {body.get('errors', 0)}")
                
                # Interpretación
                if body.get('new_indexed', 0) == 0:
                    if body.get('total_new_found', 0) == 0:
                        print(f"\n💡 INTERPRETACIÓN: No hay documentos nuevos para indexar")
                    else:
                        print(f"\n⚠️  INTERPRETACIÓN: Se encontraron documentos nuevos pero hubo errores")
                else:
                    print(f"\n🎉 INTERPRETACIÓN: Se indexaron exitosamente {body.get('new_indexed')} documentos nuevos")
                
                # Mostrar detalles
                if 'results' in body and body['results']:
                    print(f"\n📄 DOCUMENTOS PROCESADOS:")
                    for i, res in enumerate(body['results'], 1):
                        doc = res.get('document', 'Unknown')
                        
                        if res.get('success'):
                            icon = "🆕"
                            status = "INDEXADO"
                        else:
                            icon = "❌"
                            status = "ERROR"
                            
                        print(f"      {i}. {icon} {doc} - {status}")
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
    execute_index_new_only()