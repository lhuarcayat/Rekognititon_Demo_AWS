const express = require('express');
const cors = require('cors');
const multer = require('multer');
const AWS = require('aws-sdk');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3001;

// Configurar AWS
const requiredEnvVars = ['AWS_REGION', 'S3_BUCKET'];
const missingEnvVars = requiredEnvVars.filter(envVar => !process.env[envVar]);

if (missingEnvVars.lenght > 0){
  console.error('Variables de entorno faltantes:', missingEnvVars.join(', '))
  process.exit(1);
}

try {
  if (process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY) {
    // Usar credenciales directas si están disponibles
    AWS.config.update({
      accessKeyId: process.env.AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      region: process.env.AWS_REGION
    });
    console.log('AWS configurado con credenciales directas');
  } else {
    // Usar perfil de AWS
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

// Middleware
app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:3000',
  credentials: true
}));

app.use(express.json());

// Configurar multer para archivos en memoria
const upload = multer({ 
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB
  },
  fileFilter: (req, file, cb) => {
    if (file.mimetype.startsWith('image/')) {
      cb(null, true);
    } else {
      cb(new Error('Solo se permiten archivos de imagen'), false);
    }
  }
});

// Ruta para crear sesión de liveness
app.post('/api/create-liveness-session', async (req, res) => {
  try {
    const params = {
      Settings: {
        AuditImagesLimit: 4,
        OutputConfig: {
          S3Bucket: process.env.S3_BUCKET,
          S3KeyPrefix: 'liveness-sessions/'
        }
      }
    };

    const result = await rekognition.createFaceLivenessSession(params).promise();
    
    console.log('Liveness session created:', result.SessionId);
    
    res.json({
      sessionId: result.SessionId,
      status: 'success'
    });
  } catch (error) {
    console.error('Error creating liveness session:', error);
    res.status(500).json({ 
      error: error.message,
      status: 'error',
      code: error.code || 'UNKNOWN_ERROR'
    });
  } 
});

// Ruta para comparar identidad
app.post('/api/compare-identity', upload.single('documentImage'), async (req, res) => {
  try {
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
        error: 'Imagen del documento es requerido'
      });
    }

    console.log('Processing identity comparison for session:', sessionId);

    // 1. Obtener resultados de liveness
    const livenessResults = await rekognition.getFaceLivenessSessionResults({
      SessionId: sessionId
    }).promise();

    console.log('Resultados de liveness:',{
      status: livenessResults.Status,
      confidence: livenessResults.Confidence
    });

    if (livenessResults.Status !== 'SUCCEEDED') {
      return res.status(400).json({
        verified: false,
        error: 'Sesión de liveness no completada exitosamente',
        status: livenessResults.Status,
        details: {
          livenessStatus: livenessResults.Status,
          confidence: livenessResults.Confidence
        }
      });
    }

    if (!livenessResults.ReferenceImage || !livenessResults.ReferenceImage.Bytes){
      return res.status(400).json({
        verified: false,
        error: 'No se pudo obtener la imagen de referencia de liveness'
      });
    }

    // 2. Extraer imagen de referencia
    const referenceImageBytes = livenessResults.ReferenceImage.Bytes;

    // 3. Comparar caras
    const compareParams = {
      SourceImage: {
        Bytes: req.file.buffer
      },
      TargetImage: {
        Bytes: Buffer.from(referenceImageBytes, 'base64')
      },
      SimilarityThreshold: 70
    };

    const comparisonResult = await rekognition.compareFaces(compareParams).promise();

    // 4. Evaluar resultados
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
      details: {
        livenessStatus: livenessResults.Status,
        facesInDocument: comparisonResult.SourceImageFace ? 1 : 0,
        facesInLiveness: comparisonResult.TargetImageFace ? 1 : 0,
        matchesFound: comparisonResult.FaceMatches.length,
        threshold: {
          similarity: 85,
          confidence: 90 
        }
      }
    };

    console.log('Identity verification completed:', {
      sessionId,
      verified: isVerified,
      similarity: similarity.toFixed(2),
      confidence: livenessResults.Confidence.toFixed(2)
    });

    res.json(response);

  } catch (error) {
    console.error('Error in identity comparison:', error);
    res.status(500).json({
      verified: false,
      error: 'Error interno durante la comparación',
      details: error.message,
      code: error.code || 'COMPARISON_ERROR'
    });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    timestamp: new Date().toISOString(),
    version: '1.0.0',
    services: {
      aws: 'connected',
      rekognition: 'available'
    }
  });
});

app.use((error, req, res, next) => {
  if(error instanceof multer.MulterError) {
    if(error.code === 'LIMIT_FILE_SIZE'){
      return res.status(400).json({
        error: 'Archivo demasiado grande'
      });
    }
  }

  console.error('Error:', error);
  res.status(500).json({
    error: 'Error interno'
  });
});

app.listen(PORT, () => {
  console.log(`Servidor ejecutándose en puerto ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Configuración AWS Region: ${process.env.AWS_REGION}`);
  console.log(`S3 Bucket: ${process.env.S3_BUCKET}`);
});