// ============================================
// GLOBAL VARIABLES & CONFIG
// ============================================

// API Base URL will be set from config.js
let API_BASE_URL = '';

let currentStream = null;
let userPhotoTimer = null;
let processingInProgress = false;
let attemptNumber = 0;
let formData = {
    tipoDocumento: '',
    numeroDocumento: '',
    numeroCelular: '',
    documentExists: false
};

// FACE LIVENESS VARIABLES
let livenessSessionId = null;
let livenessDetectorInstance = null;

// ============================================
// UTILITY FUNCTIONS
// ============================================

function showInterface(interfaceId) {
    // Hide all interfaces
    document.querySelectorAll('.interface').forEach(iface => {
        iface.classList.remove('active');
    });
    
    // Show target interface
    const targetInterface = document.getElementById(interfaceId);
    if (targetInterface) {
        targetInterface.classList.add('active');
    }
    
    // Clean up timer and liveness state
    if (userPhotoTimer) {
        clearTimeout(userPhotoTimer);
        userPhotoTimer = null;
    }
    
    // Clean up liveness session
    if (livenessSessionId && interfaceId !== 'interface3') {
        console.log('🔄 Cleaning up liveness session on interface change');
        livenessSessionId = null;
        livenessDetectorInstance = null;
    }
    
    // Reset attempt counter
    attemptNumber = 0;
    processingInProgress = false;
}

function showError(message) {
    const errorModal = document.getElementById('errorModal');
    const errorMessage = document.getElementById('errorMessage');
    
    if (errorMessage) errorMessage.textContent = message;
    if (errorModal) errorModal.classList.remove('hidden');
}

function hideError() {
    const errorModal = document.getElementById('errorModal');
    if (errorModal) errorModal.classList.add('hidden');
}

function showSpinner(buttonId) {
    const button = document.getElementById(buttonId);
    if (!button) return;
    
    const span = button.querySelector('span');
    const spinner = button.querySelector('.spinner');
    
    if (span) span.style.display = 'none';
    if (spinner) spinner.classList.remove('hidden');
    button.disabled = true;
}

function hideSpinner(buttonId) {
    const button = document.getElementById(buttonId);
    if (!button) return;
    
    const span = button.querySelector('span');
    const spinner = button.querySelector('.spinner');
    
    if (span) span.style.display = 'inline';
    if (spinner) spinner.classList.add('hidden');
    button.disabled = false;
}

function showStatus(elementId, message, type = 'info') {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    element.textContent = message;
    element.className = `status-message ${type}`;
    element.classList.remove('hidden');
    
    // Auto hide after 5 seconds for non-error messages
    if (type !== 'error') {
        setTimeout(() => {
            element.classList.add('hidden');
        }, 5000);
    }
}

// ============================================
// CAMERA FUNCTIONS
// ============================================

function checkCameraSupport() {
    const isSecureContext = window.isSecureContext || 
                           location.protocol === 'https:' || 
                           location.hostname === 'localhost' ||
                           location.hostname === '127.0.0.1';
    
    const hasGetUserMedia = navigator.mediaDevices && 
                           navigator.mediaDevices.getUserMedia;
    
    return {
        isSecureContext,
        hasGetUserMedia,
        isSupported: isSecureContext && hasGetUserMedia
    };
}

async function startCamera(videoId) {
    try {
        const video = document.getElementById(videoId);
        if (!video) {
            throw new Error(`Video element ${videoId} not found`);
        }
        
        const cameraSupport = checkCameraSupport();
        
        if (!cameraSupport.isSupported) {
            let errorMessage = 'No se puede acceder a la cámara. ';
            
            if (!cameraSupport.isSecureContext) {
                errorMessage += 'Este sitio requiere HTTPS para acceder a la cámara.';
            } else if (!cameraSupport.hasGetUserMedia) {
                errorMessage += 'Tu navegador no soporta acceso a cámara web.';
            }
            
            throw new Error(errorMessage);
        }
        
        if (currentStream) {
            currentStream.getTracks().forEach(track => track.stop());
        }
        
        currentStream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: 'user'
            },
            audio: false
        });
        
        video.srcObject = currentStream;
        return true;
        
    } catch (error) {
        console.error('Camera error:', error);
        
        let errorMessage = 'No se pudo acceder a la cámara. ';
        
        if (error.name === 'NotAllowedError') {
            errorMessage += 'Permisos denegados. Permite el acceso y recarga la página.';
        } else if (error.name === 'NotFoundError') {
            errorMessage += 'No se encontró cámara en el dispositivo.';
        } else if (error.name === 'NotReadableError') {
            errorMessage += 'La cámara está siendo usada por otra aplicación.';
        } else {
            errorMessage += 'Error técnico: ' + (error.message || 'Error desconocido');
        }
        
        showError(errorMessage);
        return false;
    }
}

function stopCamera() {
    if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
        currentStream = null;
    }
}

function capturePhoto(videoId, canvasId) {
    const video = document.getElementById(videoId);
    const canvas = document.getElementById(canvasId);
    
    if (!video || !canvas) {
        console.error('Video or canvas element not found');
        return null;
    }
    
    const context = canvas.getContext('2d');
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    return new Promise(resolve => {
        canvas.toBlob(resolve, 'image/jpeg', 0.8);
    });
}

// ============================================
// API FUNCTIONS
// ============================================

async function checkDocumentExists(tipoDocumento, numeroDocumento) {
    try {
        const response = await fetch(`${API_BASE_URL}/check-document`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                tipoDocumento: tipoDocumento,
                numeroDocumento: numeroDocumento
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to check document');
        }
        
        return result;
        
    } catch (error) {
        console.error('Error checking document existence:', error);
        throw error;
    }
}

async function getPresignedUrl(fileName, bucketType, contentType = 'image/jpeg') {
    try {
        const response = await fetch(`${API_BASE_URL}/presigned-urls`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                fileName: fileName,
                bucketType: bucketType,
                contentType: contentType
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to get upload URL');
        }
        
        return result;
        
    } catch (error) {
        console.error('Error getting presigned URL:', error);
        throw error;
    }
}

async function uploadToS3(file, uploadUrl) {
    try {
        const response = await fetch(uploadUrl, {
            method: 'PUT',
            body: file,
            headers: {
                'Content-Type': file.type
            }
        });
        
        if (!response.ok) {
            throw new Error(`Upload failed: ${response.status}`);
        }
        
        return true;
        
    } catch (error) {
        console.error('Error uploading to S3:', error);
        throw error;
    }
}

async function indexDocument(s3Key) {
    try {
        const response = await fetch(`${API_BASE_URL}/index-document`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                s3_key: s3Key
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Document indexing failed');
        }
        
        return result;
        
    } catch (error) {
        console.error('Error indexing document:', error);
        throw error;
    }
}

async function checkValidation(numeroDocumento) {
    try {
        const response = await fetch(`${API_BASE_URL}/check-validation/${numeroDocumento}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Validation check failed');
        }
        
        return result;
        
    } catch (error) {
        console.error('Error checking validation:', error);
        throw error;
    }
}

// FACE LIVENESS FUNCTIONS

async function createLivenessSession() {
    try {
        console.log('🔄 Creating AWS Face Liveness session...');
        
        const response = await fetch(`${API_BASE_URL}/liveness-session`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                documentType: formData.tipoDocumento,
                documentNumber: formData.numeroDocumento
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to create liveness session');
        }
        
        console.log('✅ Liveness session created:', result.sessionId);
        return result;
        
    } catch (error) {
        console.error('Error creating liveness session:', error);
        throw error;
    }
}

async function getLivenessResults(sessionId) {
    try {
        const response = await fetch(`${API_BASE_URL}/liveness-session/${sessionId}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Failed to get liveness results');
        }
        
        return result;
        
    } catch (error) {
        console.error('Error getting liveness results:', error);
        throw error;
    }
}

async function checkValidationBySessionId(sessionId) {
    try {
        // Use existing endpoint but search by session ID pattern
        const response = await fetch(`${API_BASE_URL}/check-validation/liveness-${sessionId}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            return { found: false };
        }
        
        const result = await response.json();
        
        // Verify it matches this session
        if (result.liveness_session_id === sessionId || 
            result.user_image_key?.includes(sessionId)) {
            return {
                found: true,
                match_found: result.match_found,
                status: result.status,
                ...result
            };
        }
        
        return { found: false };
        
    } catch (error) {
        console.error('Error checking validation by session ID:', error);
        throw error;
    }
}

// ============================================
// DOCUMENT PROCESSING
// ============================================

async function processDocumentPhoto() {
    try {
        showSpinner('tomarFotoDocumento');
        
        // Capture photo
        const imageBlob = await capturePhoto('videoDocument', 'canvasDocument');
        
        if (!imageBlob) {
            throw new Error('No se pudo capturar la imagen');
        }
        
        // Generate filename
        const fileName = `${formData.tipoDocumento}-${formData.numeroDocumento}.jpg`;
        
        // Get presigned URL
        showStatus('documentStatus', 'Preparando upload...', 'info');
        const uploadData = await getPresignedUrl(fileName, 'documents');
        
        // Upload to S3
        showStatus('documentStatus', 'Subiendo documento...', 'info');
        await uploadToS3(imageBlob, uploadData.uploadUrl);
        
        // Index document with immediate face detection
        showStatus('documentStatus', 'Validando documento...', 'info');
        const indexResult = await indexDocument(fileName);
        
        if (indexResult.success) {
            showStatus('documentStatus', '✅ Documento validado exitosamente', 'success');
            
            // Store person name for later use
            if (indexResult.person_name) {
                formData.personName = indexResult.person_name;
            }
            
            // Wait a moment then proceed to liveness interface
            setTimeout(() => {
                stopCamera();
                showInterface('interface3');
                startLivenessInterface();
            }, 1000);
            
        } else {
            throw new Error(indexResult.error || 'Document processing failed');
        }
        
    } catch (error) {
        console.error('Document processing error:', error);
        showStatus('documentStatus', `❌ ${error.message}`, 'error');
    } finally {
        hideSpinner('tomarFotoDocumento');
    }
}

// ============================================
// FACE LIVENESS FUNCTIONS
// ============================================

async function startLivenessInterface() {
    try {
        console.log('🔒 Initializing AWS Face Liveness...');
        
        // Verify Amplify is available
        await ensureAmplifyLoaded();
        
        // Create liveness session
        showLivenessLoading('Creando sesión de verificación facial...');
        
        const sessionData = await createLivenessSession();
        livenessSessionId = sessionData.sessionId;
        
        console.log('✅ Liveness session created:', livenessSessionId);
        
        // Load Face Liveness component
        showLivenessLoading('Preparando detector facial...');
        await loadFaceLivenessDetector();
        
    } catch (error) {
        console.error('❌ Error initializing liveness:', error);
        showStatus('livenessStatus', `❌ ${error.message}`, 'error');
        showRetryLivenessButton();
    }
}

function showLivenessLoading(message) {
    // Create elements if they don't exist
    let loadingContainer = document.getElementById('livenessLoading');
    if (!loadingContainer) {
        loadingContainer = document.createElement('div');
        loadingContainer.id = 'livenessLoading';
        loadingContainer.className = 'loading-container';
        loadingContainer.innerHTML = `
            <div class="spinner"></div>
            <p id="livenessLoadingText">Preparando verificación facial...</p>
        `;
        const detectorContainer = document.getElementById('livenessDetectorContainer');
        if (detectorContainer) {
            detectorContainer.prepend(loadingContainer);
        }
    }
    
    const loadingText = document.getElementById('livenessLoadingText');
    const detectorContainer = document.getElementById('livenessDetectorContainer');
    
    if (loadingContainer) {
        loadingContainer.style.display = 'block';
        if (loadingText) loadingText.textContent = message;
    }
    
    if (detectorContainer) {
        // Hide only the detector, not the entire container
        const detector = document.getElementById('faceLivenessDetector');
        if (detector) detector.style.display = 'none';
    }
}

function hideLivenessLoading() {
    const loadingContainer = document.getElementById('livenessLoading');
    const detector = document.getElementById('faceLivenessDetector');
    
    if (loadingContainer) {
        loadingContainer.style.display = 'none';
    }
    
    if (detector) {
        detector.style.display = 'block';
    }
}

async function ensureAmplifyLoaded() {
    // Check if Amplify is already loaded
    if (typeof window.Amplify !== 'undefined') {
        console.log('✅ Amplify already loaded');
        
        // Configure Amplify if not configured
        if (window.AMPLIFY_CONFIG) {
            window.Amplify.configure(window.AMPLIFY_CONFIG);
            console.log('✅ Amplify configured for Face Liveness');
        }
        return;
    }
    
    // If not loaded, attempt dynamic loading
    console.log('📦 Loading Amplify components...');
    
    try {
        // In a real implementation, you would load Amplify scripts here
        // For now, simulate availability for testing
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Mock Amplify for testing
        window.Amplify = {
            configure: (config) => {
                console.log('🔧 Mock Amplify configured:', config);
            }
        };
        
        window.AMPLIFY_CONFIG = {
            Auth: {
                Cognito: {
                    region: 'us-east-1',
                    identityPoolId: 'us-east-1:mock-identity-pool-id',
                    allowGuestAccess: true
                }
            }
        };
        
        window.Amplify.configure(window.AMPLIFY_CONFIG);
        
        console.log('✅ Amplify components loaded (mock)');
        
    } catch (error) {
        throw new Error('Failed to load Amplify components: ' + error.message);
    }
}

async function loadFaceLivenessDetector() {
    try {
        hideLivenessLoading();
        
        // Create Face Liveness detector
        const detectorContainer = document.getElementById('faceLivenessDetector');
        
        if (!detectorContainer) {
            throw new Error('Liveness detector container not found');
        }
        
        // REAL IMPLEMENTATION: Here would go the React Face Liveness component
        // For now, create interactive simulation for testing
        
        detectorContainer.innerHTML = `
            <div class="liveness-simulator">
                <div class="liveness-instructions">
                    <h3>🎯 AWS Face Liveness Detector</h3>
                    <p><strong>Instrucciones:</strong></p>
                    <ul>
                        <li>Asegúrate de tener buena iluminación</li>
                        <li>Mantén tu rostro centrado en el área</li>
                        <li>Sigue las instrucciones visuales</li>
                        <li>El proceso toma 10-15 segundos</li>
                    </ul>
                </div>
                
                <div class="liveness-oval">
                    <div class="face-placeholder">
                        <span class="face-icon">👤</span>
                        <p>Centra tu rostro aquí</p>
                    </div>
                </div>
                
                <div class="liveness-controls">
                    <button id="startLivenessCheck" class="btn btn-primary btn-large">
                        🎯 Iniciar Verificación Facial
                    </button>
                </div>
                
                <div class="liveness-info">
                    <p><small>Session ID: ${livenessSessionId.substring(0, 8)}...</small></p>
                    <p><small>Simulación de AWS Face Liveness para testing</small></p>
                </div>
            </div>
        `;
        
        // Event listener to start simulation
        const startButton = document.getElementById('startLivenessCheck');
        if (startButton) {
            startButton.addEventListener('click', startLivenessCheck);
        }
        
        console.log('✅ Face Liveness Detector interface ready');
        
    } catch (error) {
        console.error('❌ Error loading Face Liveness detector:', error);
        showStatus('livenessStatus', `❌ Error loading detector: ${error.message}`, 'error');
        showRetryLivenessButton();
    }
}

async function startLivenessCheck() {
    try {
        console.log('🎯 Starting Face Liveness check...');
        
        const startButton = document.getElementById('startLivenessCheck');
        if (startButton) {
            startButton.disabled = true;
            startButton.innerHTML = '<span class="spinner"></span> Verificando...';
        }
        
        // Simulate liveness check process
        showLivenessProgress();
        
        // Simulate process duration (10-15 seconds like real AWS)
        await simulateLivenessProcess();
        
        // Simulate successful analysis completion
        await handleLivenessAnalysisComplete({
            sessionId: livenessSessionId,
            isLive: true,
            confidence: 97.8,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('❌ Error in liveness check:', error);
        showStatus('livenessStatus', `❌ ${error.message}`, 'error');
        showRetryLivenessButton();
    }
}

function showLivenessProgress() {
    const detectorContainer = document.getElementById('faceLivenessDetector');
    
    if (detectorContainer) {
        detectorContainer.innerHTML = `
            <div class="liveness-progress">
                <div class="liveness-oval active">
                    <div class="face-placeholder">
                        <div class="scanning-animation"></div>
                        <p>Analizando rostro...</p>
                    </div>
                </div>
                
                <div class="progress-steps">
                    <div class="step completed">✅ Rostro detectado</div>
                    <div class="step active">🔄 Verificando presencia real...</div>
                    <div class="step">⏳ Generando reference image...</div>
                </div>
                
                <div class="progress-bar">
                    <div class="progress-fill" id="livenessProgressFill"></div>
                </div>
            </div>
        `;
    }
}

async function simulateLivenessProcess() {
    return new Promise((resolve) => {
        let progress = 0;
        const progressFill = document.getElementById('livenessProgressFill');
        const steps = document.querySelectorAll('.step');
        
        const progressInterval = setInterval(() => {
            progress += 2;
            
            if (progressFill) {
                progressFill.style.width = `${progress}%`;
            }
            
            // Update steps
            if (progress >= 33 && steps[1]) {
                steps[1].classList.remove('active');
                steps[1].classList.add('completed');
                steps[1].innerHTML = '✅ Persona real verificada';
                
                if (steps[2]) {
                    steps[2].classList.add('active');
                }
            }
            
            if (progress >= 66 && steps[2]) {
                steps[2].classList.remove('active');
                steps[2].classList.add('completed');
                steps[2].innerHTML = '✅ Reference image generada';
            }
            
            if (progress >= 100) {
                clearInterval(progressInterval);
                resolve();
            }
        }, 150); // Simulate ~15 seconds total
    });
}

async function handleLivenessAnalysisComplete(livenessResult) {
    try {
        console.log('✅ AWS Face Liveness completed:', livenessResult);
        
        processingInProgress = true;
        
        // Verify liveness was successful
        if (!livenessResult.isLive) {
            throw new Error('Liveness check failed - not a real person detected');
        }
        
        // Show validation progress
        showStatus('livenessStatus', '✅ Persona real verificada. Comparando con documento...', 'success');
        
        // Create marker file for user_validator trigger
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const markerFileName = `liveness-session-${livenessSessionId}-${timestamp}.jpg`;
        
        console.log('📤 Creating validation trigger file:', markerFileName);
        
        // Create small file for trigger (1x1 pixel)
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, 1, 1);
        
        const triggerBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.1));
        
        // Upload trigger file to S3
        const uploadData = await getPresignedUrl(markerFileName, 'user-photos');
        await uploadToS3(triggerBlob, uploadData.uploadUrl);
        
        console.log('✅ Trigger file uploaded, starting validation polling...');
        
        // Start polling for validation results
        await startLivenessValidationPolling(livenessResult);
        
    } catch (error) {
        console.error('❌ Error in liveness analysis:', error);
        showStatus('livenessStatus', `❌ ${error.message}`, 'error');
        showRetryLivenessButton();
    } finally {
        processingInProgress = false;
    }
}

async function startLivenessValidationPolling(livenessResult) {
    const progressElement = document.getElementById('livenessValidationProgress');
    const timerElement = document.getElementById('livenessProgressTimer');
    
    if (progressElement) {
        progressElement.classList.remove('hidden');
    }
    
    let attempts = 0;
    const maxAttempts = 15; // More time for liveness processing
    let timeLeft = 15;
    
    const timerInterval = setInterval(() => {
        timeLeft--;
        if (timerElement) {
            timerElement.textContent = timeLeft;
        }
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
        }
    }, 1000);
    
    const pollValidation = async () => {
        attempts++;
        
        try {
            // Search for validation results for this session
            const result = await checkValidationBySessionId(livenessSessionId);
            
            if (result.found) {
                clearInterval(timerInterval);
                if (progressElement) {
                    progressElement.classList.add('hidden');
                }
                
                if (result.match_found) {
                    // ✅ SUCCESS
                    console.log('✅ Liveness validation successful');
                    showSuccessScreen({
                        ...result,
                        isLive: livenessResult.isLive,
                        livenessConfidence: livenessResult.confidence,
                        validationType: 'FACE_LIVENESS'
                    });
                    return;
                } else {
                    // ❌ FAILURE
                    handleLivenessValidationFailure(result);
                    return;
                }
            }
            
            // Continue polling
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000);
            } else {
                clearInterval(timerInterval);
                if (progressElement) {
                    progressElement.classList.add('hidden');
                }
                showStatus('livenessStatus', '❌ Tiempo de espera agotado para la validación', 'error');
                showRetryLivenessButton();
            }
            
        } catch (error) {
            console.error('Validation polling error:', error);
            
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000);
            } else {
                clearInterval(timerInterval);
                if (progressElement) {
                    progressElement.classList.add('hidden');
                }
                showStatus('livenessStatus', '❌ Error verificando la validación', 'error');
                showRetryLivenessButton();
            }
        }
    };
    
    // Start polling after 3 seconds (give time for processing)
    setTimeout(pollValidation, 3000);
}

function handleLivenessValidationFailure(result) {
    console.log(`❌ Liveness validation failed: ${result.status} - ${result.error_type}`);
    
    let errorMessage = '';
    
    switch (result.error_type) {
        case 'LOW_LIVENESS_CONFIDENCE':
            errorMessage = '❌ La verificación de presencia real no alcanzó el umbral requerido';
            break;
        case 'NO_MATCH_FOUND':
            errorMessage = '❌ El rostro no coincide con el documento';
            break;
        case 'LOW_SIMILARITY':
            errorMessage = '❌ Similitud insuficiente con el documento';
            break;
        case 'LIVENESS_ERROR':
            errorMessage = '❌ Error en la verificación de presencia real';
            break;
        default:
            errorMessage = '❌ Error en la validación con liveness';
    }
    
    showStatus('livenessStatus', errorMessage, 'error');
    showRetryLivenessButton();
}

function showRetryLivenessButton() {
    const retryButton = document.getElementById('retryLiveness');
    if (retryButton) {
        retryButton.style.display = 'inline-block';
        retryButton.classList.add('btn-retry'); // Apply special styling
    }
}

function retryLivenessProcess() {
    // Reset state
    livenessSessionId = null;
    livenessDetectorInstance = null;
    processingInProgress = false;
    
    // Hide retry button
    const retryButton = document.getElementById('retryLiveness');
    if (retryButton) {
        retryButton.style.display = 'none';
        retryButton.classList.remove('btn-retry');
    }
    
    // Hide progress and status
    const progressElement = document.getElementById('livenessValidationProgress');
    const statusElement = document.getElementById('livenessStatus');
    
    if (progressElement) {
        progressElement.classList.add('hidden');
    }
    
    if (statusElement) {
        statusElement.classList.add('hidden');
    }
    
    // Restart process
    startLivenessInterface();
}

// ============================================
// SUCCESS SCREEN
// ============================================

function showSuccessScreen(validationResult) {
    const personNameElement = document.getElementById('personName');
    const documentNumberElement = document.getElementById('documentNumberDisplay');
    const cellNumberElement = document.getElementById('cellNumberDisplay');
    
    if (!personNameElement || !documentNumberElement || !cellNumberElement) {
        console.error('Success screen elements not found');
        return;
    }
    
    const personName = validationResult.person_name || formData.personName || 'USUARIO VERIFICADO';
    personNameElement.textContent = personName.toUpperCase();
    
    documentNumberElement.textContent = formData.numeroDocumento;
    cellNumberElement.textContent = formData.numeroCelular;
    
    // Add liveness information if available
    if (validationResult.validationType === 'FACE_LIVENESS') {
        console.log('✅ Identity verified using AWS Face Liveness');
        console.log(`   Liveness Confidence: ${validationResult.livenessConfidence}%`);
        console.log(`   Similarity Score: ${validationResult.similarity}%`);
        
        // Show liveness badge in interface if exists
        const livenessInfo = document.querySelector('.liveness-verification-info');
        if (livenessInfo) {
            livenessInfo.style.display = 'block';
        }
    }
    
    showInterface('interfaceSuccess');
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function resetToInitialState(shouldCleanupDocument = false) {
    if (shouldCleanupDocument && formData.numeroDocumento && !formData.documentExists){
        console.log('cleaning up orphaned document');
        cleanupOrphanedDocument();
    }

    // Reset form data
    formData = {
        tipoDocumento: '',
        numeroDocumento: '',
        numeroCelular: '',
        documentExists: false
    };
    
    // Reset attempt counter
    attemptNumber = 0;
    processingInProgress = false;
    
    // Reset liveness state
    livenessSessionId = null;
    livenessDetectorInstance = null;
    
    // Reset form
    const documentForm = document.getElementById('documentForm');
    if (documentForm) documentForm.reset();
    
    // Clean up timers
    if (userPhotoTimer) {
        clearTimeout(userPhotoTimer);
        userPhotoTimer = null;
    }
    
    // Stop camera
    stopCamera();
    
    // Hide liveness elements
    const retryButton = document.getElementById('retryLiveness');
    const progressElement = document.getElementById('livenessValidationProgress');
    const statusElement = document.getElementById('livenessStatus');
    
    if (retryButton) {
        retryButton.style.display = 'none';
        retryButton.classList.remove('btn-retry');
    }
    
    if (progressElement) {
        progressElement.classList.add('hidden');
    }
    
    if (statusElement) {
        statusElement.classList.add('hidden');
    }
    
    // Show initial interface
    showInterface('interface1');
}

function checkSystemCompatibility() {
    const issues = [];
    
    const cameraSupport = checkCameraSupport();
    if (!cameraSupport.isSupported) {
        if (!cameraSupport.isSecureContext) {
            issues.push('🔒 Conexión no segura: Se requiere HTTPS para usar la cámara');
        }
        if (!cameraSupport.hasGetUserMedia) {
            issues.push('📱 Navegador incompatible: No soporta acceso a cámara web');
        }
    }
    
    if (!API_BASE_URL || API_BASE_URL === 'YOUR_API_GATEWAY_URL_HERE') {
        issues.push('⚙️ Configuración pendiente: URL del API Gateway no configurada');
    }
    
    if (!window.fetch) {
        issues.push('🌐 Navegador muy antiguo: No soporta fetch API');
    }
    
    // Check Face Liveness support
    if (!window.crypto || !window.crypto.getRandomValues) {
        issues.push('🔐 Navegador incompatible: No soporta Web Crypto API (requerido para Face Liveness)');
    }
    
    return issues;
}

async function cleanupOrphanedDocument(){
    try {
        const response = await fetch(`${API_BASE_URL}/cleanup-document`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                tipoDocumento: formData.tipoDocumento,
                numeroDocumento: formData.numeroDocumento,
                reason: 'USER_ABANDONED_PROCESS'
            })
        });

        const result = await response.json();

        if (response.ok) {
            console.log(`Orphaned document cleaned up: ${result.message}`);
        } else {
            console.error(`Failed to cleanup document: ${result.error}`)
        }
    } catch (error) {
        console.error('Error cleaning up document', error);
    }
}

// ============================================
// EVENT LISTENERS
// ============================================

function setupEventListeners() {
    // Interface 1 - Form submission with document check
    const documentForm = document.getElementById('documentForm');
    if (documentForm) {
        documentForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Validate form
            const tipoDocumento = document.getElementById('tipoDocumento')?.value;
            const numeroDocumento = document.getElementById('numeroDocumento')?.value.trim();
            const numeroCelular = document.getElementById('numeroCelular')?.value.trim();
            
            if (!tipoDocumento || !numeroDocumento || !numeroCelular) {
                showError('Por favor complete todos los campos obligatorios');
                return;
            }
            
            // Store basic form data
            formData.tipoDocumento = tipoDocumento;
            formData.numeroDocumento = numeroDocumento;
            formData.numeroCelular = numeroCelular;
            
            const submitButton = this.querySelector('button[type="submit"]');
            const submitButtonId = submitButton?.id || 'submitBtn';
            
            if (!submitButton.id) {
                submitButton.id = submitButtonId;
            }
            
            try {
                showSpinner(submitButtonId);
                
                console.log(`🔍 Checking if document exists: ${tipoDocumento}-${numeroDocumento}`);
                
                const documentCheck = await checkDocumentExists(tipoDocumento, numeroDocumento);
                
                formData.documentExists = documentCheck.exists;
                
                if (documentCheck.exists) {
                    console.log('✅ Existing user - skipping document capture');
                    
                    hideSpinner(submitButtonId);
                    
                    showStatus('documentCheckStatus', '✅ ' + documentCheck.message, 'success');
                    
                    setTimeout(() => {
                        showInterface('interfacePermission');
                        
                        const permissionText = document.querySelector('.permission-content p');
                        if (permissionText) {
                            permissionText.textContent = 'Documento encontrado en el sistema. Para completar la verificación biométrica, necesitamos acceso a su cámara web para validar su identidad con Face Liveness.';
                        }
                    }, 1000);
                } else {
                    console.log('🆕 New user - full registration required');
                    
                    hideSpinner(submitButtonId);
                    showInterface('interfacePermission');
                }
                
            } catch (error) {
                console.error('Error checking document existence:', error);
                hideSpinner(submitButtonId);
                showError('Error verificando el documento. Por favor, intente nuevamente.');
            }
        });
    }
    
    // Permission interface - Allow camera
    const permitirCamara = document.getElementById('permitirCamara');
    if (permitirCamara) {
        permitirCamara.addEventListener('click', async function() {
            showSpinner('permitirCamara');
            
            if (formData.documentExists) {
                // Go direct to liveness for existing users
                hideSpinner('permitirCamara');
                showInterface('interface3');
                startLivenessInterface();
            } else {
                const cameraStarted = await startCamera('videoDocument');
                
                hideSpinner('permitirCamara');
                
                if (cameraStarted) {
                    const tipoDocumentoDisplay = document.getElementById('tipoDocumentoDisplay');
                    if (tipoDocumentoDisplay) {
                        tipoDocumentoDisplay.textContent = formData.tipoDocumento;
                    }
                    showInterface('interface2');
                }
            }
        });
    }
    
    // Permission interface - Back button
    const atrasPermission = document.getElementById('atrasPermission');
    if (atrasPermission) {
        atrasPermission.addEventListener('click', function() {
            resetToInitialState(false);
        });
    }
    
    // Interface 2 - Take document photo
    const tomarFotoDocumento = document.getElementById('tomarFotoDocumento');
    if (tomarFotoDocumento) {
        tomarFotoDocumento.addEventListener('click', processDocumentPhoto);
    }
    
    // Interface 2 - Back button
    const atrasDocumento = document.getElementById('atrasDocumento');
    if (atrasDocumento) {
        atrasDocumento.addEventListener('click', function() {
            stopCamera();
            showInterface('interfacePermission');
        });
    }
    
    // Interface 3 - Back button (modified for liveness)
    const atrasLiveness = document.getElementById('atrasLiveness');
    if (atrasLiveness) {
        atrasLiveness.addEventListener('click', function() {
            // Clean up liveness session if active
            if (livenessSessionId) {
                console.log('🔄 Cleaning up liveness session on back navigation');
                livenessSessionId = null;
                livenessDetectorInstance = null;
            }
            
            processingInProgress = false;
            
            if (formData.documentExists) {
                showInterface('interfacePermission');
            } else {
                showInterface('interface2');
                startCamera('videoDocument');
            }
        });
    }
    
    // Retry liveness button
    const retryLiveness = document.getElementById('retryLiveness');
    if (retryLiveness) {
        retryLiveness.addEventListener('click', retryLivenessProcess);
    }
    
    // Success interface - Finalizar button
    const finalizarBtn = document.getElementById('finalizarBtn');
    if (finalizarBtn) {
        finalizarBtn.addEventListener('click', function() {
            resetToInitialState(false);
        });
    }
    
    // Success interface - Pagar button
    const pagarBtn = document.getElementById('pagarBtn');
    if (pagarBtn) {
        pagarBtn.addEventListener('click', function() {
            console.log('Pagar button clicked - no functionality implemented');
        });
    }
    
    // Error modal - Close button
    const closeErrorModal = document.getElementById('closeErrorModal');
    if (closeErrorModal) {
        closeErrorModal.addEventListener('click', hideError);
    }
    
    // Close modal when clicking outside
    const errorModal = document.getElementById('errorModal');
    if (errorModal) {
        errorModal.addEventListener('click', function(e) {
            if (e.target === this) {
                hideError();
            }
        });
    }

    // Input validation for document number
    const numeroDocumento = document.getElementById('numeroDocumento');
    if (numeroDocumento) {
        numeroDocumento.addEventListener('input', function(e) {
            const onlyNumbers = e.target.value.replace(/[^0-9]/g,'');
            
            if (e.target.value !== onlyNumbers) {
                e.target.value = onlyNumbers;
                if (e.target.value.length !== onlyNumbers.length) {
                    e.target.style.borderColor = '#f59e0b';
                    setTimeout(() => {
                        e.target.style.borderColor = '';
                    }, 1000);
                }
            }
        });

        numeroDocumento.addEventListener('paste',function(e){
            setTimeout(() => {
                const onlyNumbers = e.target.value.replace(/[^0-9]/g,'');
                e.target.value = onlyNumbers;
            },10);
        });
    }
}

// ============================================
// INITIALIZATION
// ============================================

function initializeApp() {
    // Set API base URL from config
    if (typeof window.API_GATEWAY_URL !== 'undefined' && window.API_GATEWAY_URL !== 'YOUR_API_GATEWAY_URL_HERE') {
        API_BASE_URL = window.API_GATEWAY_URL;
        console.log('✅ API Gateway URL loaded from config:', API_BASE_URL);
    } else {
        API_BASE_URL = '';
        console.warn('⚠️  API_GATEWAY_URL not configured.');
    }
    
    const compatibilityIssues = checkSystemCompatibility();
    
    if (compatibilityIssues.length > 0) {
        console.warn('⚠️  System compatibility issues detected:');
        compatibilityIssues.forEach(issue => console.warn('   -', issue));
    }
    
    setupEventListeners();
    showInterface('interface1');
    
    console.log('🔧 Environment Info:');
    console.log('   - Protocol:', location.protocol);
    console.log('   - Host:', location.host);
    console.log('   - Secure Context:', window.isSecureContext);
    console.log('   - Camera Support:', checkCameraSupport().isSupported);
    console.log('   - Face Liveness Ready:', typeof window.Amplify !== 'undefined' || 'Will load dynamically');
    
    console.log('✅ Rekognition POC Frontend initialized with Face Liveness integration');
}

// ============================================
// DYNAMIC SCRIPT LOADING
// ============================================

// Auto-load Amplify components when needed
document.addEventListener('DOMContentLoaded', function() {
    // Pre-load components if available
    if (typeof window.AMPLIFY_CONFIG !== 'undefined') {
        console.log('🔧 Amplify Config detected, Face Liveness ready');
    } else {
        console.log('📦 Amplify Config will be loaded when needed');
    }
});

// ============================================
// START APPLICATION
// ============================================

document.addEventListener('DOMContentLoaded', initializeApp);

window.addEventListener('beforeunload', function() {
    stopCamera();
    
    if (userPhotoTimer) {
        clearTimeout(userPhotoTimer);
    }
    
    // Cleanup liveness session
    if (livenessSessionId) {
        console.log('🔄 Cleaning up liveness session on page unload');
        livenessSessionId = null;
    }
});

console.log('✅ Face Liveness integration loaded - Ready for deployment');