import React, { useState, useEffect } from 'react';
import { FaceLivenessDetector } from '@aws-amplify/ui-react-liveness';
import { Button, Card, Text, Loader, View } from '@aws-amplify/ui-react';
import { verificationService } from '../services/verificationService';

function LivenessCheck({ documentImage, onComplete, onError }) {
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    createLivenessSession();
  }, []);

  const createLivenessSession = async () => {
    try {
      setLoading(true);
      const session = await verificationService.createLivenessSession();
      setSessionId(session.sessionId);
    } catch (error) {
      onError('Error al inicializar la verificación: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAnalysisComplete = async (livenessResult) => {
    console.log('Liveness completado:', livenessResult);
    
    if (!livenessResult.isLive) {
      onError('No se pudo verificar que seas una persona real. Intenta de nuevo.');
      return;
    }

    try {
      // Realizar comparación con el documento
      const comparisonResult = await verificationService.compareWithDocument(
        documentImage,
        sessionId
      );
      
      onComplete({
        ...livenessResult,
        ...comparisonResult,
        sessionId
      });
    } catch (error) {
      onError('Error en la comparación: ' + error.message);
    }
  };

  const handleError = (error) => {
    console.error('Error en liveness:', error);
    onError('Error durante la verificación facial: ' + error.message);
  };

  return (
    <Card className="liveness-card">
      <Text fontSize="xl" fontWeight="bold" marginBottom="20px">
        Paso 2: Verificación facial en vivo
      </Text>
      
      <Text marginBottom="20px" color="gray">
        Mira directamente a la cámara y sigue las instrucciones en pantalla
      </Text>

      {loading ? (
        <View className="loading-container">
          <Loader size="large" />
          <Text marginTop="10px">Iniciando cámara...</Text>
        </View>
      ) : sessionId ? (
        <View className="liveness-detector-container">
          <FaceLivenessDetector
            sessionId={sessionId}
            region={process.env.REACT_APP_AWS_REGION}
            onAnalysisComplete={handleAnalysisComplete}
            onError={handleError}
            config={{
              faceDistanceThreshold: 0.3,
              faceDistanceThresholdMax: 0.8,
            }}
          />
        </View>
      ) : (
        <View className="error-container">
          <Text color="red">Error al inicializar la cámara</Text>
          <Button onClick={createLivenessSession} marginTop="10px">
            Reintentar
          </Button>
        </View>
      )}
    </Card>
  );
}

export default LivenessCheck;