import React from 'react';
import { Button, Card, Text, Alert, View, Badge } from '@aws-amplify/ui-react';

function VerificationResult({ result, onReset }) {
  const isVerified = result?.verified || false;
  const similarity = result?.similarity || 0;
  const confidence = result?.confidence || 0;

  return (
    <Card className="result-card">
      <Text fontSize="xl" fontWeight="bold" marginBottom="20px">
        Resultado de la Verificación
      </Text>

      <Alert
        variation={isVerified ? 'success' : 'error'}
        hasIcon={true}
        className="result-alert"
      >
        <Text fontWeight="bold">
          {isVerified 
            ? '✅ Identidad Verificada Exitosamente' 
            : '❌ No se pudo verificar la identidad'
          }
        </Text>
      </Alert>

      <View className="metrics-container">
        <Text fontWeight="bold" marginBottom="15px">Métricas de verificación:</Text>
        
        <View className="metric-row">
          <Text>Persona real detectada:</Text>
          <Badge variation={result?.isLive ? 'success' : 'error'}>
            {result?.isLive ? 'Sí' : 'No'}
          </Badge>
        </View>

        <View className="metric-row">
          <Text>Confianza facial:</Text>
          <Badge variation={confidence > 90 ? 'success' : confidence > 70 ? 'warning' : 'error'}>
            {confidence.toFixed(1)}%
          </Badge>
        </View>

        <View className="metric-row">
          <Text>Similitud con documento:</Text>
          <Badge variation={similarity > 85 ? 'success' : similarity > 70 ? 'warning' : 'error'}>
            {similarity.toFixed(1)}%
          </Badge>
        </View>

        <View className="metric-row">
          <Text>Umbral requerido:</Text>
          <Text>85%</Text>
        </View>
      </View>

      {isVerified && (
        <Alert variation="info" className="success-message">
          🎉 Tu identidad ha sido verificada correctamente. 
          Puedes proceder con total seguridad.
        </Alert>
      )}

      {!isVerified && (
        <Alert variation="warning" className="retry-message">
          ⚠️ La verificación no fue exitosa. Esto puede deberse a:
          <ul>
            <li>Mala iluminación durante la verificación</li>
            <li>Documento poco claro</li>
            <li>Movimiento excesivo</li>
          </ul>
        </Alert>
      )}

      <Button
        onClick={onReset}
        variation="primary"
        size="large"
        className="reset-button"
      >
        Nueva Verificación
      </Button>
    </Card>
  );
}

export default VerificationResult;