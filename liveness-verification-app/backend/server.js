const express = require('express');
const cors = require('cors');
const multer = require('multer');
const AWS = require('aws-sdk');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3001;

// Configurar AWS
try {
  if (process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY) {
    AWS.config.update({
      accessKeyId: process.env.AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      region: process.env.AWS_REGION
    });
    console.log('AWS configurado con credenciales directas');
  } else {
    const credentials = new AWS.SharedIniFileCredentials({
      profile: process.env.AWS_PROFILE || 'default'
    });
    AWS.config.credentials = credentials;
    AWS.config.update({
      region: process.env.AWS_REGION
    });
    console.log('AWS configurado con perfil:', process.env.AWS_PROFILE || 'default');
  }
} catch (error) {
  console.error('Error configurando AWS:', error.message);
  process.exit(1);
}

const rekognition = new AWS.Rekognition();
const s3 = new AWS.S3(); // ← Necesario para descargar fotos de S3

// Middleware
app.use(cors({
  origin: ['http://localhost:3000', 'https://localhost:3000'],
  credentials: true
}));

app.use(express.json());

// Configurar multer
const upload = multer({ 
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 }
});

// 🆕 Función para descargar la foto desde S3
async function downloadImageFromS3(s3Object) {
  try {
    console.log('📥 Descargando foto de S3:', {
      bucket: s3Object.Bucket,
      key: s3Object.Name
    });
    
    const params = {
      Bucket: s3Object.Bucket,
      Key: s3Object.Name
    };
    
    const s3Response = await s3.getObject(params).promise();
    console.log('✅ Foto descargada de S3 exitosamente, tamaño:', s3Response.Body.length, 'bytes');
    
    return s3Response.Body;
  } catch (error) {
    console.error('❌ Error descargando de S3:', error);
    throw new Error('No pude descargar la foto de S3: ' + error.message);
  }
}

// 🆕 Función inteligente para obtener la foto (desde S3 o bytes directos)
async function getReferenceImageBytes(livenessResults) {
  const referenceImage = livenessResults.ReferenceImage;
  
  if (!referenceImage) {
    throw new Error('No hay reference image en los resultados');
  }
  
  // Opción 1: Si hay bytes directos, usarlos
  if (referenceImage.Bytes) {
    console.log('💾 Usando bytes directos (no está en S3)');
    return Buffer.from(referenceImage.Bytes, 'base64');
  }
  
  // Opción 2: Si está en S3, descargarla
  if (referenceImage.S3Object) {
    console.log('🗄️ La foto está en S3, descargando...');
    return await downloadImageFromS3(referenceImage.S3Object);
  }
  
  throw new Error('La reference image no tiene ni bytes ni está en S3');
}

// Función para obtener resultados de liveness con logging mejorado
async function getLivenessResults(sessionId) {
  try {
    console.log('🔍 Obteniendo resultados para session:', sessionId);
    
    const livenessResults = await rekognition.getFaceLivenessSessionResults({
      SessionId: sessionId
    }).promise();

    console.log('📊 Liveness Status:', livenessResults.Status);
    console.log('📊 Liveness Confidence:', livenessResults.Confidence);
    
    // Verificar dónde está la reference image
    const referenceImage = livenessResults.ReferenceImage;
    if (referenceImage) {
      const hasBytes = !!(referenceImage.Bytes);
      const hasS3Object = !!(referenceImage.S3Object);
      
      console.log('📸 Reference Image ubicación:', {
        tieneBytes: hasBytes,
        estaEnS3: hasS3Object,
        detallesS3: hasS3Object ? {
          bucket: referenceImage.S3Object.Bucket,
          archivo: referenceImage.S3Object.Name
        } : null
      });
    } else {
      console.log('⚠️ No hay reference image aún');
    }

    return livenessResults;
  } catch (error) {
    console.error('❌ Error getting liveness results:', error);
    throw error;
  }
}

// Ruta para crear sesión (MANTIENE S3 para guardar fotos)
app.post('/api/create-liveness-session', async (req, res) => {
  try {
    const params = {
      Settings: {
        AuditImagesLimit: 4,
        // ✅ MANTENER S3 para guardar las fotos
        OutputConfig: {
          S3Bucket: process.env.S3_BUCKET,
          S3KeyPrefix: 'liveness-sessions/'
        }
      }
    };

    const result = await rekognition.createFaceLivenessSession(params).promise();
    
    console.log('✅ Liveness session created:', result.SessionId);
    console.log('🗄️ Las fotos se guardarán en S3:', process.env.S3_BUCKET);
    
    res.json({
      sessionId: result.SessionId,
      status: 'success',
      storageLocation: `s3://${process.env.S3_BUCKET}/liveness-sessions/`
    });
  } catch (error) {
    console.error('❌ Error creating liveness session:', error);
    res.status(500).json({ 
      error: error.message,
      status: 'error',
      code: error.code || 'UNKNOWN_ERROR'
    });
  } 
});

// Ruta para verificar si la foto está disponible (en S3 o bytes)
app.get('/api/check-reference-image/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    
    console.log('🔍 Verificando disponibilidad de foto para session:', sessionId);
    
    if (!sessionId) {
      return res.status(400).json({
        referenceImageAvailable: false,
        error: 'Session ID es requerido'
      });
    }

    const livenessResults = await rekognition.getFaceLivenessSessionResults({
      SessionId: sessionId
    }).promise();

    const referenceImage = livenessResults.ReferenceImage;
    const hasBytes = !!(referenceImage?.Bytes);
    const hasS3Object = !!(referenceImage?.S3Object);
    const isAvailable = hasBytes || hasS3Object;
    
    console.log(`📊 Estado de la foto:`, {
      sessionId: sessionId,
      status: livenessResults.Status,
      confidence: livenessResults.Confidence,
      fotoDisponible: isAvailable,
      ubicacion: hasS3Object ? 'S3' : hasBytes ? 'Bytes directos' : 'No disponible'
    });

    res.json({
      referenceImageAvailable: isAvailable,
      sessionStatus: livenessResults.Status,
      confidence: livenessResults.Confidence,
      sessionId: sessionId,
      storageLocation: hasS3Object ? 'S3' : hasBytes ? 'direct_bytes' : 'none',
      s3Details: hasS3Object ? referenceImage.S3Object : null
    });

  } catch (error) {
    console.error('❌ Error checking reference image:', error);
    
    if (error.code === 'SessionNotFoundException') {
      return res.status(404).json({
        referenceImageAvailable: false,
        error: 'Sesión no encontrada',
        code: 'SESSION_NOT_FOUND'
      });
    }

    res.status(500).json({
      referenceImageAvailable: false,
      error: 'Error verificando reference image: ' + error.message,
      code: error.code || 'UNKNOWN_ERROR'
    });
  }
});

// 🎯 Ruta de comparación que FUNCIONA con S3
app.post('/api/compare-identity', upload.single('documentImage'), async (req, res) => {
  try {
    console.log('\n🔥 === COMPARACIÓN CON SOPORTE S3 COMPLETO ===');
    console.log('📋 Request info:', {
      body: req.body,
      file: req.file ? { name: req.file.originalname, size: req.file.size } : null,
      timestamp: new Date().toISOString()
    });

    const { sessionId } = req.body;
    
    if (!sessionId) {
      return res.status(400).json({
        verified: false,
        error: 'Session ID es requerido'
      });
    }

    if (!req.file) {
      return res.status(400).json({
        verified: false,
        error: 'Imagen del documento es requerida'
      });
    }

    console.log('📊 Obteniendo resultados de liveness...');
    
    try {
      const livenessResults = await getLivenessResults(sessionId);
      
      if (livenessResults.Status !== 'SUCCEEDED') {
        console.log('⚠️ Liveness status no exitoso:', livenessResults.Status);
        return res.status(400).json({
          verified: false,
          error: `Sesión de liveness no exitosa: ${livenessResults.Status}`,
          sessionStatus: livenessResults.Status
        });
      }

      // Verificar si hay reference image (en S3 o bytes)
      const referenceImage = livenessResults.ReferenceImage;
      const hasBytes = !!(referenceImage?.Bytes);
      const hasS3Object = !!(referenceImage?.S3Object);
      const isAvailable = hasBytes || hasS3Object;

      if (!isAvailable) {
        console.log('⚠️ Reference image aún no disponible');
        
        return res.status(400).json({
          verified: false,
          error: 'AWS aún está procesando y guardando la foto en S3. Intenta en unos segundos.',
          code: 'REFERENCE_IMAGE_NOT_AVAILABLE',
          retryable: true,
          sessionStatus: livenessResults.Status,
          confidence: livenessResults.Confidence,
          details: {
            message: 'La foto se está subiendo a S3, espera unos segundos',
            bucket: process.env.S3_BUCKET
          }
        });
      }

      console.log('✅ Reference image disponible, procediendo con comparación...');
      console.log(`📸 Ubicación: ${hasS3Object ? 'S3' : 'Bytes directos'}`);

      // 🎯 AQUÍ ESTÁ LA MAGIA: Obtener la foto desde donde esté
      const referenceImageBytes = await getReferenceImageBytes(livenessResults);

      // Realizar comparación con AWS Rekognition
      const compareParams = {
        SourceImage: { Bytes: req.file.buffer }, // Documento subido
        TargetImage: { Bytes: referenceImageBytes }, // Foto del liveness (desde S3 o bytes)
        SimilarityThreshold: 70
      };

      const comparisonResult = await rekognition.compareFaces(compareParams).promise();
      
      const similarity = comparisonResult.FaceMatches.length > 0 
        ? comparisonResult.FaceMatches[0].Similarity 
        : 0;

      const isVerified = similarity >= 85 && livenessResults.Confidence > 90;

      const response = {
        verified: isVerified,
        isLive: livenessResults.Confidence > 90,
        confidence: Math.round(livenessResults.Confidence * 100) / 100,
        similarity: Math.round(similarity * 100) / 100,
        sessionId: sessionId,
        timestamp: new Date().toISOString(),
        storageLocation: hasS3Object ? 'S3' : 'direct_bytes',
        s3Details: hasS3Object ? referenceImage.S3Object : null,
        details: {
          livenessStatus: livenessResults.Status,
          facesInDocument: comparisonResult.SourceImageFace ? 1 : 0,
          facesInLiveness: 1,
          matchesFound: comparisonResult.FaceMatches.length,
          photoSource: hasS3Object ? 'downloaded_from_s3' : 'direct_bytes'
        }
      };

      console.log('✅ Comparación exitosa:', {
        verified: isVerified,
        similarity: similarity.toFixed(2),
        confidence: livenessResults.Confidence.toFixed(2),
        photoLocation: hasS3Object ? 'S3' : 'Direct'
      });

      res.json(response);

    } catch (livenessError) {
      console.error('❌ Error obteniendo liveness results:', livenessError);
      
      if (livenessError.code === 'SessionNotFoundException') {
        return res.status(400).json({
          verified: false,
          error: 'Sesión no encontrada. Verifica que el Session ID sea correcto.',
          code: 'SESSION_NOT_FOUND',
          sessionId: sessionId
        });
      }

      return res.status(500).json({
        verified: false,
        error: 'Error obteniendo resultados de liveness: ' + livenessError.message,
        code: livenessError.code || 'LIVENESS_ERROR'
      });
    }

  } catch (error) {
    console.error('❌ Error general:', error);
    res.status(500).json({
      verified: false,
      error: 'Error interno: ' + error.message
    });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    timestamp: new Date().toISOString(),
    version: 'S3-ENABLED-1.0.0',
    s3Bucket: process.env.S3_BUCKET,
    features: ['S3 Storage', 'Auto Download', 'Face Comparison']
  });
});

app.listen(PORT, () => {
  console.log(`🔧 SERVIDOR CON SOPORTE S3 ejecutándose en puerto ${PORT}`);
  console.log(`🗄️ Las fotos se guardarán en S3: ${process.env.S3_BUCKET}`);
  console.log(`🎯 La comparación funciona descargando automáticamente de S3`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`AWS Region: ${process.env.AWS_REGION}`);
});