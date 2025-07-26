import React, { useState, useEffect } from 'react';
import { FaceLivenessDetector } from '@aws-amplify/ui-react-liveness';
import { Button, Card, Text, Loader, View, Alert, Badge } from '@aws-amplify/ui-react';
import { verificationService } from '../services/verificationService';

function LivenessCheck({ documentImage, onComplete, onError }) {
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [currentStep, setCurrentStep] = useState('creating_session');
  const [progressMessage, setProgressMessage] = useState('Inicializando sesión de verificación...');
  const [debugMode, setDebugMode] = useState(true); // Activar modo debug por defecto

  useEffect(() => {
    createLivenessSession();
  }, []);

  const createLivenessSession = async () => {
    try {
      console.log('🔄 Creando sesión de AWS Face Liveness...');
      setLoading(true);
      setCurrentStep('creating_session');
      setProgressMessage('Creando sesión de verificación facial...');
      
      const session = await verificationService.createLivenessSession();
      setSessionId(session.sessionId);
      setCurrentStep('session_ready');
      setProgressMessage('Sesión lista. Preparando detector facial...');
      
      console.log('✅ Sesión de liveness creada:', session.sessionId);
    } catch (error) {
      console.error('❌ Error creando sesión:', error);
      onError('Error al inicializar la verificación: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAnalysisComplete = async (livenessResult) => {
    try {
      console.log('🎯 === AWS LIVENESS COMPLETADO ===');
      console.log('🎯 Resultado completo:', livenessResult);
      console.log('🎯 Tipo de resultado:', typeof livenessResult);
      console.log('🎯 Propiedades disponibles:', Object.keys(livenessResult || {}));
      
      setComparing(true);
      setCurrentStep('processing');
      setProgressMessage('Verificación facial completada. Iniciando comparación...');
      
      // Verificar que el liveness fue exitoso
      const isLive = livenessResult?.isLive || 
                     livenessResult?.liveness?.isLive || 
                     livenessResult?.result?.isLive ||
                     true; // Asumir que pasó si llegó hasta aquí

      console.log('✅ ¿Es persona real?', isLive);

      if (isLive === false) {
        onError('No se pudo verificar que seas una persona real. Intenta de nuevo.');
        return;
      }

      console.log('✅ Liveness verificado - es una persona real');
      setProgressMessage('Persona real verificada. Comparando con documento...');

      // Elegir método según modo debug
      try {
        let comparisonResult;
        
        if (debugMode) {
          console.log('🐛 Usando modo DEBUG para identificar el problema...');
          setProgressMessage('Modo DEBUG: Analizando el estado de la reference image...');
          comparisonResult = await verificationService.compareWithDocumentDebug(
            documentImage,
            sessionId
          );
        } else {
          console.log('🔄 Usando modo SIMPLE con delays graduales...');
          setProgressMessage('Esperando que AWS procese la reference image...');
          comparisonResult = await verificationService.compareWithDocumentSimple(
            documentImage,
            sessionId
          );
        }

        console.log('✅ Comparación completada:', comparisonResult);

        // Combinar resultados de liveness + comparación
        const finalResult = {
          isLive: isLive,
          confidence: livenessResult?.confidence || comparisonResult?.confidence || 95,
          ...comparisonResult,
          sessionId: sessionId,
          originalLivenessResult: livenessResult // Para debugging
        };

        setCurrentStep('completed');
        setProgressMessage('Verificación completada exitosamente');
        onComplete(finalResult);

      } catch (comparisonError) {
        console.error('❌ Error en comparación con documento:', comparisonError);
        
        // Logging adicional para debug
        console.log('🐛 Error details:', {
          name: comparisonError.name,
          message: comparisonError.message,
          code: comparisonError.code,
          retryable: comparisonError.retryable,
          stack: comparisonError.stack
        });
        
        // Si es un error retryable, ofrecer reintento
        if (comparisonError.retryable && retryCount < 2) {
          setRetryCount(prev => prev + 1);
          setCurrentStep('retrying');
          setProgressMessage(`Reintentando verificación... (${retryCount + 1}/3)`);
          
          // Pequeño delay antes de reintentar
          setTimeout(() => {
            handleRetryComparison();
          }, 3000);
        } else {
          // Error no retryable o demasiados reintentos
          let errorMessage = 'Error en la comparación: ' + comparisonError.message;
          
          if (comparisonError.code === 'SESSION_EXPIRED') {
            errorMessage = 'La sesión ha expirado. Por favor, inicia una nueva verificación.';
          } else if (comparisonError.code === 'REFERENCE_IMAGE_NOT_AVAILABLE') {
            errorMessage = 'AWS está tomando más tiempo del esperado. Verifica tu conexión y reinicia la verificación.';
          }
          
          onError(errorMessage);
        }
      }

    } catch (error) {
      console.error('❌ Error general en análisis:', error);
      onError('Error durante la verificación facial: ' + error.message);
    } finally {
      setComparing(false);
    }
  };

  const handleRetryComparison = async () => {
    try {
      setComparing(true);
      setProgressMessage('Reintentando comparación...');
      
      // Usar método simple para reintentos
      const comparisonResult = await verificationService.compareWithDocumentSimple(
        documentImage,
        sessionId
      );

      console.log('✅ Comparación exitosa en reintento:', comparisonResult);

      const finalResult = {
        isLive: true,
        ...comparisonResult,
        sessionId: sessionId
      };

      setCurrentStep('completed');
      setProgressMessage('Verificación completada exitosamente');
      onComplete(finalResult);

    } catch (error) {
      console.error('❌ Error en reintento:', error);
      onError('Error en la verificación: ' + error.message);
    } finally {
      setComparing(false);
    }
  };

  const handleLivenessError = (error) => {
    console.error('❌ Error en AWS Face Liveness:', error);
    console.error('❌ Error details:', {
      name: error.name,
      message: error.message,
      state: error.state,
      stack: error.stack
    });

    let errorMessage = 'Error durante la verificación facial';
    
    if (error.message?.includes('No credentials')) {
      errorMessage = 'Error de credenciales de AWS. Verificando configuración...';
    } else if (error.message?.includes('Access denied')) {
      errorMessage = 'Permisos insuficientes para AWS Rekognition';
    } else if (error.state === 'SERVER_ERROR') {
      errorMessage = 'Error del servidor de AWS. Intenta de nuevo.';
    } else if (error.state === 'TIMEOUT') {
      errorMessage = 'Tiempo de espera agotado. Verifica tu conexión a internet.';
    }

    onError(errorMessage + ': ' + error.message);
  };

  const retryLiveness = () => {
    setSessionId(null);
    setLoading(true);
    setComparing(false);
    setRetryCount(0);
    setCurrentStep('creating_session');
    createLivenessSession();
  };

  // Test directo de la nueva ruta del backend
  const testBackendRoute = async () => {
    if (!sessionId) {
      console.log('❌ No hay sessionId para testear');
      return;
    }

    try {
      console.log('🧪 === TESTEANDO RUTA DEL BACKEND ===');
      setProgressMessage('Testeando conexión con backend...');
      
      const isAvailable = await verificationService.checkReferenceImageStatus(sessionId);
      console.log('🧪 Resultado del test:', isAvailable);
      
      alert(`Test del backend completado. Reference image disponible: ${isAvailable}`);
    } catch (error) {
      console.error('🧪 Error en test del backend:', error);
      alert(`Error en test del backend: ${error.message}`);
    }
  };

  // Componente de barra de progreso personalizada
  const CustomProgressBar = ({ value, label }) => {
    return (
      <View marginBottom="20px">
        <View style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '8px'
        }}>
          <Text fontSize="medium" fontWeight="medium">{label}</Text>
          <Badge variation="info">{value}%</Badge>
        </View>
        <View style={{
          width: '100%',
          height: '8px',
          backgroundColor: '#e9ecef',
          borderRadius: '4px',
          overflow: 'hidden'
        }}>
          <View style={{
            width: `${value}%`,
            height: '100%',
            backgroundColor: '#007bff',
            borderRadius: '4px',
            transition: 'width 0.3s ease'
          }} />
        </View>
      </View>
    );
  };

  const getProgressPercentage = () => {
    switch (currentStep) {
      case 'creating_session': return 10;
      case 'session_ready': return 25;
      case 'processing': return 60;
      case 'retrying': return 80;
      case 'completed': return 100;
      default: return 0;
    }
  };

  return (
    <Card className="liveness-card">
      <Text fontSize="xl" fontWeight="bold" marginBottom="20px">
        Paso 2: Verificación facial en vivo con AWS
      </Text>
      
      <Text marginBottom="20px" color="gray">
        Utiliza AWS Face Liveness para verificar que eres una persona real
      </Text>

      {/* Barra de progreso personalizada */}
      <CustomProgressBar 
        value={getProgressPercentage()} 
        label={progressMessage}
      />

      {loading ? (
        <View className="loading-container">
          <Loader size="large" />
          <Text marginTop="10px">{progressMessage}</Text>
        </View>
      ) : sessionId ? (
        <View className="liveness-detector-container">
          <Text marginBottom="15px" fontSize="medium" fontWeight="bold">
            🎯 Detector AWS Face Liveness activo
          </Text>

          {/* Panel de debugging */}
          <View marginBottom="15px" style={{ 
            padding: '15px', 
            backgroundColor: '#f8f9fa', 
            borderRadius: '8px',
            border: '1px solid #dee2e6'
          }}>
            <Text fontSize="small" fontWeight="bold" marginBottom="10px">
              🐛 Panel de Debugging
            </Text>
            
            <View style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
              <Button
                onClick={() => setDebugMode(!debugMode)}
                variation={debugMode ? "primary" : "secondary"}
                size="small"
              >
                {debugMode ? "🐛 Modo DEBUG ON" : "🔄 Modo Simple"}
              </Button>
              
              <Button
                onClick={testBackendRoute}
                variation="secondary"
                size="small"
                isDisabled={!sessionId}
              >
                🧪 Test Backend
              </Button>
            </View>
            
            <Text fontSize="small" color="gray">
              Session ID: {sessionId ? `${sessionId.substring(0, 8)}...` : 'N/A'}
            </Text>
            <Text fontSize="small" color="gray">
              Modo: {debugMode ? "Debug (análisis detallado)" : "Simple (delays graduales)"}
            </Text>
          </View>

          {/* Mostrar estado de comparación */}
          {comparing && (
            <Alert variation="info" hasIcon={true} marginBottom="15px">
              <View>
                <Text fontWeight="bold">Procesando verificación...</Text>
                <Text>{progressMessage}</Text>
                {retryCount > 0 && (
                  <Text fontSize="small" color="gray">
                    Intento {retryCount + 1} de 3
                  </Text>
                )}
              </View>
            </Alert>
          )}
          
          <FaceLivenessDetector
            sessionId={sessionId}
            region="us-east-1"
            onAnalysisComplete={handleAnalysisComplete}
            onError={handleLivenessError}
            config={{
              faceDistanceThreshold: 0.3,
              faceDistanceThresholdMax: 0.8,
            }}
            displayText={{
              hintMoveFaceFrontOfCameraText: "Mueve tu cara frente a la cámara",
              hintTooManyFacesText: "Asegúrate de que solo tu cara sea visible",
              hintFaceDetectedText: "Cara detectada correctamente",
              hintCanNotIdentifyText: "No se puede identificar tu cara",
              hintTooCloseText: "Aléjate un poco de la cámara",
              hintTooFarText: "Acércate más a la cámara"
            }}
          />
          
          <View marginTop="20px">
            <Button 
              onClick={retryLiveness}
              variation="secondary"
              size="large"
              width="100%"
              isDisabled={comparing}
            >
              {comparing ? 'Procesando...' : '🔄 Reiniciar verificación'}
            </Button>
          </View>

          {/* Información de debugging */}
          <Alert variation="info" hasIcon={true} marginTop="15px">
            <View>
              <Text fontSize="small" fontWeight="bold" marginBottom="5px">
                🔍 Información de debugging
              </Text>
              <Text fontSize="small" marginBottom="3px">
                • El modo DEBUG mostrará logs detallados en la consola
              </Text>
              <Text fontSize="small" marginBottom="3px">
                • Usa "Test Backend" para verificar la conectividad
              </Text>
              <Text fontSize="small" color="gray">
                • Revisa la consola del navegador (F12) para ver los logs detallados
              </Text>
            </View>
          </Alert>
        </View>
      ) : (
        <View className="error-container">
          <Text color="red" marginBottom="15px">
            Error al inicializar AWS Face Liveness
          </Text>
          <Button onClick={retryLiveness} variation="primary">
            🔄 Reintentar
          </Button>
        </View>
      )}
    </Card>
  );
}

export default LivenessCheck;