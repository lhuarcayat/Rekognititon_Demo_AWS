import React from 'react';
import { Button, Card, Text, Alert, View, Badge, Divider } from '@aws-amplify/ui-react';

function VerificationResult({ result, onReset }) {
  const isVerified = result?.verified || false;
  const similarity = result?.similarity || 0;
  const confidence = result?.confidence || 0;
  const sessionId = result?.sessionId;
  const timestamp = result?.timestamp;

  const getStatusIcon = () => {
    return isVerified ? '✅' : '❌';
  };

  const getStatusColor = () => {
    return isVerified ? 'success' : 'error';
  };

  const getBadgeVariation = (value, thresholds) => {
    if (value >= thresholds.excellent) return 'success';
    if (value >= thresholds.good) return 'warning';
    return 'error';
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleString('es-ES', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const getRecommendations = () => {
    const recommendations = [];
    
    if (!isVerified) {
      if (confidence < 90) {
        recommendations.push('La verificación facial no alcanzó el umbral de confianza mínimo (90%)');
      }
      
      if (similarity < 85) {
        recommendations.push('La similitud entre el documento y la verificación facial es baja');
      }
      
      recommendations.push('Asegúrate de tener buena iluminación');
      recommendations.push('Mantén el documento claro y sin reflejos');
      recommendations.push('Evita movimientos excesivos durante la verificación');
    }
    
    return recommendations;
  };

  return (
    <Card className="result-card">
      <Text fontSize="xl" fontWeight="bold" marginBottom="20px">
        {getStatusIcon()} Resultado de la Verificación
      </Text>

      {/* Alert principal con resultado */}
      <Alert
        variation={getStatusColor()}
        hasIcon={true}
        className="result-alert"
      >
        <View>
          <Text fontWeight="bold" fontSize="large">
            {isVerified 
              ? 'Identidad Verificada Exitosamente' 
              : 'No se pudo verificar la identidad'
            }
          </Text>
          {timestamp && (
            <Text fontSize="small" marginTop="5px">
              Verificado el: {formatTimestamp(timestamp)}
            </Text>
          )}
        </View>
      </Alert>

      {/* Métricas detalladas */}
      <View className="metrics-container">
        <Text fontWeight="bold" marginBottom="15px" fontSize="large">
          📊 Métricas de verificación
        </Text>
        
        <View className="metric-row">
          <Text fontWeight="medium">Persona real detectada:</Text>
          <Badge variation={result?.isLive ? 'success' : 'error'}>
            {result?.isLive ? '✅ Sí' : '❌ No'}
          </Badge>
        </View>

        <View className="metric-row">
          <Text fontWeight="medium">Confianza facial:</Text>
          <Badge variation={getBadgeVariation(confidence, { excellent: 95, good: 85 })}>
            {confidence.toFixed(1)}%
          </Badge>
        </View>

        <View className="metric-row">
          <Text fontWeight="medium">Similitud con documento:</Text>
          <Badge variation={getBadgeVariation(similarity, { excellent: 90, good: 80 })}>
            {similarity.toFixed(1)}%
          </Badge>
        </View>

        <Divider size="small" />

        <View className="metric-row">
          <Text fontWeight="medium">Umbral de similitud requerido:</Text>
          <Text color="gray">85%</Text>
        </View>

        <View className="metric-row">
          <Text fontWeight="medium">Umbral de confianza requerido:</Text>
          <Text color="gray">90%</Text>
        </View>

        {sessionId && (
          <>
            <Divider size="small" />
            <View className="metric-row">
              <Text fontWeight="medium" fontSize="small">ID de sesión:</Text>
              <Text fontSize="small" color="gray" style={{ fontFamily: 'monospace' }}>
                {sessionId.substring(0, 8)}...
              </Text>
            </View>
          </>
        )}
      </View>

      {/* Detalles técnicos adicionales */}
      {result?.details && (
        <View marginTop="20px">
          <Text fontWeight="bold" marginBottom="10px" fontSize="medium">
            🔧 Detalles técnicos
          </Text>
          <View style={{ 
            backgroundColor: '#f8f9fa', 
            padding: '15px', 
            borderRadius: '8px',
            fontSize: '12px'
          }}>
            <Text fontSize="small">Estado de liveness: {result.details.livenessStatus}</Text>
            <Text fontSize="small">Caras detectadas en documento: {result.details.facesInDocument}</Text>
            <Text fontSize="small">Caras detectadas en verificación: {result.details.facesInLiveness}</Text>
            <Text fontSize="small">Coincidencias encontradas: {result.details.matchesFound}</Text>
          </View>
        </View>
      )}

      {/* Mensaje de éxito */}
      {isVerified && (
        <Alert variation="success" className="success-message" hasIcon={true}>
          <View>
            <Text fontWeight="bold">🎉 Verificación Exitosa</Text>
            <Text>
              Tu identidad ha sido verificada correctamente. Puedes proceder con total seguridad.
            </Text>
            <Text fontSize="small" marginTop="5px" color="green">
              • Persona real confirmada ({confidence.toFixed(1)}% de confianza)
              <br />
              • Documento coincide ({similarity.toFixed(1)}% de similitud)
              <br />
              • Verificación completada exitosamente
            </Text>
          </View>
        </Alert>
      )}

      {/* Recomendaciones en caso de fallo */}
      {!isVerified && (
        <Alert variation="warning" className="retry-message" hasIcon={true}>
          <View>
            <Text fontWeight="bold">⚠️ Verificación no exitosa</Text>
            <Text marginBottom="10px">
              La verificación no cumplió con los requisitos de seguridad.
            </Text>
            
            {getRecommendations().length > 0 && (
              <View>
                <Text fontWeight="medium" marginBottom="5px">Recomendaciones:</Text>
                {getRecommendations().map((recommendation, index) => (
                  <Text key={index} fontSize="small" marginBottom="2px">
                    • {recommendation}
                  </Text>
                ))}
              </View>
            )}
          </View>
        </Alert>
      )}

      {/* Botones de acción */}
      <View marginTop="25px">
        <Button
          onClick={onReset}
          variation="primary"
          size="large"
          className="reset-button"
          style={{ width: '100%' }}
        >
          {isVerified ? '🔄 Nueva Verificación' : '🔄 Intentar de Nuevo'}
        </Button>
        
        {isVerified && (
          <Text fontSize="small" textAlign="center" marginTop="10px" color="gray">
            O continúa con el siguiente paso de tu proceso de verificación
          </Text>
        )}
      </View>

      {/* Información adicional de seguridad */}
      <Alert variation="info" hasIcon={true} marginTop="15px">
        <View>
          <Text fontWeight="bold" fontSize="small">🔒 Información de seguridad</Text>
          <Text fontSize="small">
            Esta verificación utiliza AWS Rekognition Face Liveness, una tecnología 
            avanzada que detecta intentos de suplantación usando fotos, videos o máscaras. 
            Tus datos biométricos no se almacenan permanentemente.
          </Text>
        </View>
      </Alert>
    </Card>
  );
}

export default VerificationResult;