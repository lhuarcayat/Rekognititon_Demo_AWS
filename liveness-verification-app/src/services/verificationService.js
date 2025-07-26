class VerificationService {
  constructor() {
    this.apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:3001';
  }

  async createLivenessSession() {
    try {
      console.log('🔄 Creando sesión AWS Rekognition...');
      const response = await fetch(`${this.apiUrl}/api/create-liveness-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('✅ Sesión creada en backend:', data);
      return data;
    } catch (error) {
      console.error('❌ Error creando sesión:', error);
      throw error;
    }
  }

  // Función auxiliar para crear delay
  delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // Método mejorado para verificar reference image status con debugging
  async checkReferenceImageStatus(sessionId) {
    try {
      console.log('🔍 === DEBUGGING REFERENCE IMAGE STATUS ===');
      console.log('🔍 Session ID:', sessionId);
      console.log('🔍 URL completa:', `${this.apiUrl}/api/check-reference-image/${sessionId}`);
      
      const response = await fetch(`${this.apiUrl}/api/check-reference-image/${sessionId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      console.log('📥 Status de respuesta:', response.status);
      console.log('📥 Headers de respuesta:', response.headers);

      if (response.ok) {
        const data = await response.json();
        console.log('✅ Datos recibidos del backend:', data);
        return data.referenceImageAvailable;
      } else {
        const errorText = await response.text();
        console.error('❌ Error response:', errorText);
        return false;
      }
      
    } catch (error) {
      console.error('❌ Error checking reference image status:', error);
      return false;
    }
  }

  // Versión simplificada sin polling complicado
  async compareWithDocumentSimple(documentImage, sessionId) {
    try {
      console.log('🔄 === COMPARACIÓN SIMPLE CON DELAYS GRADUALES ===');
      console.log('🔄 Documento:', documentImage ? {
        name: documentImage.name,
        size: documentImage.size,
        type: documentImage.type
      } : 'NULL');
      console.log('🔄 Session ID:', sessionId);

      if (!documentImage) {
        throw new Error('Imagen del documento requerida');
      }

      if (!sessionId) {
        throw new Error('Session ID requerido');
      }

      const formData = new FormData();
      formData.append('documentImage', documentImage);
      formData.append('sessionId', sessionId);

      // Intentar comparación con delays crecientes
      const delays = [2000, 4000, 6000, 8000, 10000]; // 2, 4, 6, 8, 10 segundos
      
      for (let i = 0; i < delays.length; i++) {
        const currentDelay = delays[i];
        console.log(`⏳ Intento ${i + 1}/${delays.length} - Esperando ${currentDelay}ms...`);
        
        await this.delay(currentDelay);
        
        try {
          console.log(`📤 Enviando al backend (intento ${i + 1})...`);

          const response = await fetch(`${this.apiUrl}/api/compare-identity`, {
            method: 'POST',
            body: formData,
          });

          console.log(`📥 Respuesta recibida:`, response.status, response.statusText);

          if (response.ok) {
            const data = await response.json();
            console.log('✅ Comparación exitosa:', data);
            return data;
          }

          // Si no es OK, intentar parsear el error
          const errorData = await response.json().catch(() => ({ error: 'Error desconocido' }));
          
          console.log('❌ Error del backend:', errorData);

          // Si es reference image no disponible, continuar con el siguiente delay
          if (errorData.code === 'REFERENCE_IMAGE_NOT_AVAILABLE' && i < delays.length - 1) {
            console.log(`⏳ Reference image aún no disponible. Continuando con delay más largo...`);
            continue;
          }

          // Si no es retryable o es el último intento, lanzar error
          const error = new Error(errorData.error || `HTTP error! status: ${response.status}`);
          error.code = errorData.code;
          error.retryable = errorData.retryable || false;
          error.details = errorData.details;
          throw error;

        } catch (fetchError) {
          // Si es el último intento, lanzar el error
          if (i === delays.length - 1) {
            throw fetchError;
          }
          
          console.log(`🌐 Error en intento ${i + 1}, continuando...`, fetchError.message);
        }
      }

    } catch (error) {
      console.error('❌ Error en comparación simple:', error);
      throw error;
    }
  }

  // Método con debugging paso a paso para usar en lugar del polling
  async compareWithDocumentDebug(documentImage, sessionId) {
    try {
      console.log('🐛 === MODO DEBUG COMPLETO ===');
      
      // Paso 1: Verificar estado inmediatamente
      console.log('🐛 Paso 1: Verificando estado inmediatamente...');
      let isReady = await this.checkReferenceImageStatus(sessionId);
      console.log('🐛 Reference image lista inmediatamente?', isReady);
      
      if (isReady) {
        console.log('🐛 ¡La reference image ya está lista! Procediendo directamente...');
        return await this.makeDirectComparison(documentImage, sessionId);
      }

      // Paso 2: Esperar un poco y verificar de nuevo
      console.log('🐛 Paso 2: Esperando 3 segundos y verificando de nuevo...');
      await this.delay(3000);
      isReady = await this.checkReferenceImageStatus(sessionId);
      console.log('🐛 Reference image lista después de 3s?', isReady);
      
      if (isReady) {
        console.log('🐛 Reference image lista después de 3s! Procediendo...');
        return await this.makeDirectComparison(documentImage, sessionId);
      }

      // Paso 3: Intentar comparación directa aunque no esté "lista"
      console.log('🐛 Paso 3: Status dice que no está lista, pero intentando comparación directa...');
      return await this.makeDirectComparison(documentImage, sessionId);

    } catch (error) {
      console.error('🐛 Error en debug mode:', error);
      throw error;
    }
  }

  // Método auxiliar para hacer la comparación directa
  async makeDirectComparison(documentImage, sessionId) {
    try {
      console.log('🔄 Haciendo comparación directa...');
      
      const formData = new FormData();
      formData.append('documentImage', documentImage);
      formData.append('sessionId', sessionId);

      const response = await fetch(`${this.apiUrl}/api/compare-identity`, {
        method: 'POST',
        body: formData,
      });

      console.log(`📥 Respuesta de comparación directa:`, response.status);

      if (response.ok) {
        const data = await response.json();
        console.log('✅ Comparación directa exitosa:', data);
        return data;
      }

      const errorData = await response.json().catch(() => ({ error: 'Error desconocido' }));
      console.log('❌ Error en comparación directa:', errorData);
      
      const error = new Error(errorData.error || `HTTP error! status: ${response.status}`);
      error.code = errorData.code;
      error.retryable = errorData.retryable || false;
      throw error;

    } catch (error) {
      console.error('❌ Error haciendo comparación directa:', error);
      throw error;
    }
  }

  // Mantener el método original para backward compatibility
  async compareWithDocument(documentImage, sessionId, options = {}) {
    // Usar la versión simple por defecto
    return await this.compareWithDocumentSimple(documentImage, sessionId);
  }

  // Método nuevo que permite elegir el modo de debugging
  async compareWithDocumentSmart(documentImage, sessionId) {
    // Usar el modo debug para obtener más información
    return await this.compareWithDocumentDebug(documentImage, sessionId);
  }
}

export const verificationService = new VerificationService();