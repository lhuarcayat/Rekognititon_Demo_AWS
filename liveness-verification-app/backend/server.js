const express = require('express');
const cors = require('cors');
const multer = require('multer');
const AWS = require('aws-sdk');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3001;

// Configurar AWS
const credentials = new AWS.sharedInifileCredentials({profile: process.env.AWS_PROFILE || 'default'});
AWS.config.credentials = credentials;
AWS.config.update({
    region: process.env.AWS_REGION || 'us-east-1'
});


//AWS.config.update({
//  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
//  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
//  region: process.env.AWS_REGION || 'us-east-1'
//});

const rekognition = new AWS.Rekognition();

// Middleware
app.use(cors());
app.use(express.json());

// Configurar multer para archivos en memoria
const upload = multer({ 
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB
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
      status: 'error'
    });
  }
});

// Ruta para comparar identidad
app.post('/api/compare-identity', upload.single('documentImage'), async (req, res) => {
  try {
    const { sessionId } = req.body;
    const documentImageBuffer = req.file.buffer;

    console.log('Processing identity comparison for session:', sessionId);

    // 1. Obtener resultados de liveness
    const livenessResults = await rekognition.getFaceLivenessSessionResults({
      SessionId: sessionId
    }).promise();

    if (livenessResults.Status !== 'SUCCEEDED') {
      return res.status(400).json({
        verified: false,
        error: 'Sesión de liveness no completada exitosamente',
        status: livenessResults.Status
      });
    }

    // 2. Extraer imagen de referencia
    const referenceImageBytes = livenessResults.ReferenceImage.Bytes;

    // 3. Comparar caras
    const compareParams = {
      SourceImage: {
        Bytes: documentImageBuffer
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
        matchesFound: comparisonResult.FaceMatches.length
      }
    };

    console.log('Identity verification completed:', {
      sessionId,
      verified: isVerified,
      similarity,
      confidence: livenessResults.Confidence
    });

    res.json(response);

  } catch (error) {
    console.error('Error in identity comparison:', error);
    res.status(500).json({
      verified: false,
      error: 'Error interno durante la comparación',
      details: error.message
    });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`📡 Health check: http://localhost:${PORT}/health`);
});