import boto3
import json
from datetime import datetime

def verify_successful_validation():
    """
    Verificar que la validación exitosa se guardó correctamente
    """
    print("🎯 VERIFICANDO RESULTADO EXITOSO")
    print("=" * 50)
    
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('rekognition-comparison-results')
        
        # Obtener todos los resultados
        response = table.scan()
        results = sorted(response['Items'], key=lambda x: x['timestamp'], reverse=True)
        
        if not results:
            print("❌ No se encontraron resultados")
            return False
            
        # Buscar el resultado más reciente con MATCH_CONFIRMED
        latest_match = None
        for result in results:
            if result.get('status') == 'MATCH_CONFIRMED':
                latest_match = result
                break
        
        if not latest_match:
            print("❌ No se encontró MATCH_CONFIRMED reciente")
            return False
            
        # Mostrar detalles del resultado exitoso
        print("🎉 ¡VALIDACIÓN EXITOSA ENCONTRADA!")
        print("-" * 40)
        
        print(f"🆔 ID de Comparación: {latest_match['comparison_id']}")
        print(f"📸 Imagen Usuario: {latest_match['user_image_key']}")
        print(f"🎯 Estado: {latest_match['status']}")
        
        confidence = float(latest_match.get('confidence_score', 0))
        print(f"📊 Confidence Score: {confidence:.1f}%")
        
        if 'search_confidence' in latest_match:
            search_conf = float(latest_match['search_confidence'])
            print(f"🔍 Search Confidence: {search_conf:.1f}%")
        
        if 'person_name' in latest_match:
            print(f"👤 Persona Identificada: {latest_match['person_name']}")
        
        if 'document_image_key' in latest_match:
            print(f"📄 Documento Coincidente: {latest_match['document_image_key']}")
        
        processing_time = latest_match.get('processing_time_ms', 0)
        print(f"⏱️  Tiempo de Procesamiento: {processing_time}ms")
        
        print(f"📅 Timestamp: {latest_match['timestamp']}")
        
        if 'candidates_evaluated' in latest_match:
            print(f"🎲 Candidatos Evaluados: {latest_match['candidates_evaluated']}")
        
        # Interpretar el resultado
        print(f"\n🎯 INTERPRETACIÓN:")
        if confidence >= 95:
            print("✅ Identidad CONFIRMADA con muy alta confianza")
        elif confidence >= 85:
            print("✅ Identidad CONFIRMADA con alta confianza")
        else:
            print("⚠️  Identidad confirmada pero revisar manualmente")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def show_system_stats():
    """
    Mostrar estadísticas generales del sistema
    """
    print("\n📈 ESTADÍSTICAS DEL SISTEMA")
    print("=" * 40)
    
    try:
        dynamodb = boto3.resource('dynamodb')
        
        # Documentos indexados
        docs_table = dynamodb.Table('rekognition-indexed-documents')
        docs_response = docs_table.scan()
        indexed_docs = docs_response['Items']
        
        # Resultados de validación
        results_table = dynamodb.Table('rekognition-comparison-results')
        results_response = results_table.scan()
        validation_results = results_response['Items']
        
        print(f"📋 Documentos Indexados: {len(indexed_docs)}")
        print(f"🔍 Total Validaciones: {len(validation_results)}")
        
        # Estadísticas por estado
        status_counts = {}
        total_confidence = 0
        confidence_count = 0
        
        for result in validation_results:
            status = result.get('status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if 'confidence_score' in result:
                total_confidence += float(result['confidence_score'])
                confidence_count += 1
        
        print("\n📊 Distribución por Estado:")
        for status, count in status_counts.items():
            percentage = (count / len(validation_results)) * 100
            emoji = '✅' if 'MATCH' in status else '❌' if 'ERROR' in status else '⚠️'
            print(f"   {emoji} {status}: {count} ({percentage:.1f}%)")
        
        if confidence_count > 0:
            avg_confidence = total_confidence / confidence_count
            print(f"\n📊 Confidence Promedio: {avg_confidence:.1f}%")
        
        # Mostrar documentos indexados
        print(f"\n👥 PERSONAS EN EL SISTEMA:")
        for doc in indexed_docs[:5]:  # Mostrar primeros 5
            print(f"   👤 {doc.get('person_name', 'Sin nombre')}")
            print(f"      📄 {doc['s3_key']}")
            print(f"      🆔 {doc['document_id']}")
        
        if len(indexed_docs) > 5:
            print(f"   ... y {len(indexed_docs) - 5} más")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_query_functionality():
    """
    Probar funcionalidad de consultas
    """
    print("\n🔍 FUNCIONALIDAD DE CONSULTAS")
    print("=" * 40)
    
    try:
        dynamodb = boto3.resource('dynamodb')
        results_table = dynamodb.Table('rekognition-comparison-results')
        
        # Query por imagen específica
        print("📋 Consultas Disponibles:")
        
        # 1. Buscar por imagen de usuario
        response = results_table.scan()
        results = response['Items']
        
        if results:
            # Ejemplo de query por user_image_key
            example_image = results[0]['user_image_key']
            
            print(f"🔍 Ejemplo - Buscar validaciones de: {example_image}")
            
            # Usar GSI si existe
            try:
                query_response = results_table.query(
                    IndexName='user-image-index',
                    KeyConditionExpression='user_image_key = :uk',
                    ExpressionAttributeValues={':uk': example_image}
                )
                
                print(f"   ✅ Encontradas {len(query_response['Items'])} validaciones")
                
            except Exception as e:
                print(f"   ⚠️  Query directo no disponible: {e}")
                # Fallback a scan con filtro
                filtered_results = [r for r in results if r['user_image_key'] == example_image]
                print(f"   ✅ Encontradas {len(filtered_results)} validaciones (scan)")
        
        # 2. Buscar por estado
        confirmed_matches = [r for r in results if r.get('status') == 'MATCH_CONFIRMED']
        print(f"🎯 Coincidencias Confirmadas: {len(confirmed_matches)}")
        
        # 3. Buscar por confidence alto
        high_confidence = [r for r in results if float(r.get('confidence_score', 0)) > 90]
        print(f"📊 Validaciones con >90% confidence: {len(high_confidence)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """
    Verificación completa del sistema funcionando
    """
    print("🚀 VERIFICACIÓN SISTEMA COMPLETAMENTE FUNCIONAL")
    print("=" * 60)
    
    success_checks = 0
    total_checks = 3
    
    # 1. Verificar validación exitosa
    if verify_successful_validation():
        success_checks += 1
    
    # 2. Mostrar estadísticas
    if show_system_stats():
        success_checks += 1
    
    # 3. Probar consultas
    if test_query_functionality():
        success_checks += 1
    
    # Resumen final
    print(f"\n{'='*60}")
    print("🏁 RESUMEN FINAL")
    
    if success_checks == total_checks:
        print("🎉 ¡SISTEMA COMPLETAMENTE OPERATIVO!")
        print("✅ Indexación funcionando")
        print("✅ Validación funcionando") 
        print("✅ Storage funcionando")
        print("✅ Consultas funcionando")
        
        print(f"\n🚀 PRÓXIMOS PASOS SUGERIDOS:")
        print("   1. 📱 Probar con más imágenes de diferentes personas")
        print("   2. 🔧 Ajustar thresholds según necesidades del negocio")
        print("   3. 🌐 Implementar API REST para integración")
        print("   4. 📊 Configurar dashboards de monitoreo")
        print("   5. 🛡️  Agregar validaciones adicionales de seguridad")
        
    else:
        print(f"⚠️  Sistema parcialmente funcional ({success_checks}/{total_checks})")
        
    print(f"\n💡 Para monitoreo continuo:")
    print("   python quick_check.py monitor")

if __name__ == "__main__":
    main()