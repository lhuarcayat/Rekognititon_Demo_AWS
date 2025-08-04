// ============================================
// CORRECTED AWS FACE LIVENESS IMPLEMENTATION
// ============================================

// Global variables
let API_BASE_URL = '';
let currentStream = null;
let processingInProgress = false;
let formData = {
    tipoDocumento: '',
    numeroDocumento: '',
    numeroCelular: '',
    documentExists: false
};

// AWS Face Liveness variables
let livenessSessionId = null;
let awsAmplifyConfigured = false;

// ============================================
// CORRECTED AWS AMPLIFY CONFIGURATION FOR V6
// ============================================

function configureAmplify() {
    if (awsAmplifyConfigured) return;
    
    try {
        // ✅ CORRECT: Amplify v6 configuration
        const { Amplify } = window.Amplify;
        
        Amplify.configure({
            Auth: {
                Cognito: {
                    identityPoolId: window.LIVENESS_IDENTITY_POOL_ID,
                    region: 'us-east-1',
                    allowGuestAccess: true
                }
            }
        });
        
        awsAmplifyConfigured = true;
        console.log('✅ AWS Amplify v6 configured for Face Liveness');
        console.log('   Identity Pool:', window.LIVENESS_IDENTITY_POOL_ID);
        
    } catch (error) {
        console.error('❌ Error configuring Amplify:', error);
        throw new Error('Failed to configure AWS Amplify v6');
    }
}

// ============================================
// CORRECTED AWS FACE LIVENESS FUNCTIONS
// ============================================

async function startRealFaceLiveness() {
    try {
        console.log('🔒 Starting REAL AWS Face Liveness...');
        
        showStatus('livenessStatus', 'Iniciando AWS Face Liveness...', 'info');
        
        // Step 1: Configure Amplify
        configureAmplify();
        
        // Step 2: Create liveness session
        const sessionData = await createLivenessSession();
        livenessSessionId = sessionData.sessionId;
        
        console.log('✅ Liveness session created:', livenessSessionId);
        
        // Step 3: Mount REAL Face Liveness component
        await mountRealFaceLivenessComponent();
        
    } catch (error) {
        console.error('❌ Error starting Face Liveness:', error);
        showStatus('livenessStatus', `❌ Error: ${error.message}`, 'error');
        showRetryButton();
    }
}

async function createLivenessSession() {
    try {
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
        
        return result;
        
    } catch (error) {
        console.error('Error creating liveness session:', error);
        throw error;
    }
}

async function mountRealFaceLivenessComponent() {
    try {
        const mountPoint = document.getElementById('faceLivenessMount');
        if (!mountPoint) {
            throw new Error('Mount point not found');
        }
        
        // Clear loading placeholder
        mountPoint.innerHTML = '';
        
        console.log('🎯 Mounting REAL AWS FaceLivenessDetector component...');
        
        // ✅ CORRECT: Get FaceLivenessDetector from Amplify UI React
        const { FaceLivenessDetector } = window.AmplifyUIReact;
        
        if (!FaceLivenessDetector) {
            throw new Error('FaceLivenessDetector component not found in AmplifyUIReact');
        }
        
        console.log('✅ FaceLivenessDetector component found');
        
        // ✅ CORRECT: React component props for REAL Face Liveness
        const livenessProps = {
            sessionId: livenessSessionId,
            region: 'us-east-1',
            onAnalysisComplete: handleLivenessComplete,
            onError: handleLivenessError,
            // Additional configuration
            config: {
                faceMovementChallenge: 'FaceMovementAndLightChallenge'
            }
        };
        
        // ✅ CORRECT: Create and render REAL React component
        const livenessElement = React.createElement(FaceLivenessDetector, livenessProps);
        
        // ✅ CORRECT: Render using ReactDOM
        const { createRoot } = ReactDOM;
        const root = createRoot(mountPoint);
        root.render(livenessElement);
        
        console.log('✅ REAL AWS FaceLivenessDetector mounted successfully');
        showStatus('livenessStatus', '🎯 AWS Face Liveness iniciado - Siga las instrucciones', 'success');
        
    } catch (error) {
        console.error('❌ Error mounting Face Liveness component:', error);
        
        // Enhanced error information
        console.log('Debug info:');
        console.log('  AmplifyUIReact available:', typeof window.AmplifyUIReact !== 'undefined');
        console.log('  FaceLivenessDetector available:', 
                   typeof window.AmplifyUIReact !== 'undefined' && 
                   typeof window.AmplifyUIReact.FaceLivenessDetector !== 'undefined');
        
        throw error;
    }
}

function handleLivenessComplete(analysisResult) {
    try {
        console.log('✅ REAL AWS Face Liveness completed');
        console.log('Analysis result:', analysisResult);
        
        showStatus('livenessStatus', '✅ Liveness verificado. Procesando resultados...', 'success');
        
        processingInProgress = true;
        
        // Get liveness results from AWS
        setTimeout(async () => {
            try {
                const results = await getLivenessResults(livenessSessionId);
                
                console.log('REAL Liveness results:', results);
                
                if (results.status !== 'SUCCEEDED') {
                    throw new Error(`Liveness check failed: ${results.status}`);
                }
                
                // Store liveness confidence for display
                const livenessConfidence = results.confidence || 0;
                
                // Create validation trigger
                await createValidationTrigger(livenessSessionId);
                
                // Start polling for validation results
                await startValidationPolling(livenessSessionId, livenessConfidence);
                
            } catch (error) {
                console.error('❌ Error processing liveness results:', error);
                showStatus('livenessStatus', `❌ ${error.message}`, 'error');
                showRetryButton();
            } finally {
                processingInProgress = false;
            }
        }, 1000);
        
    } catch (error) {
        console.error('❌ Error in liveness completion:', error);
        showStatus('livenessStatus', `❌ ${error.message}`, 'error');
        showRetryButton();
        processingInProgress = false;
    }
}

function handleLivenessError(error) {
    console.error('❌ REAL Face Liveness error:', error);
    
    let errorMessage = 'Error en Face Liveness';
    
    if (error && error.message) {
        errorMessage = error.message;
    } else if (typeof error === 'string') {
        errorMessage = error;
    } else if (error && error.error) {
        errorMessage = error.error;
    }
    
    showStatus('livenessStatus', `❌ ${errorMessage}`, 'error');
    showRetryButton();
    processingInProgress = false;
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

async function createValidationTrigger(sessionId) {
    try {
        // Create a marker file to trigger user_validator Lambda
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const markerFileName = `liveness-session-${sessionId}-${timestamp}.jpg`;
        
        console.log('📤 Creating validation trigger:', markerFileName);
        
        // Create minimal trigger file
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, 1, 1);
        
        const triggerBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.1));
        
        // Upload trigger file
        const uploadData = await getPresignedUrl(markerFileName, 'user-photos');
        await uploadToS3(triggerBlob, uploadData.uploadUrl);
        
        console.log('✅ Validation trigger created');
        
    } catch (error) {
        console.error('Error creating validation trigger:', error);
        throw error;
    }
}

async function startValidationPolling(sessionId, livenessConfidence) {
    showStatus('livenessStatus', '🔄 Validando con documento...', 'info');
    
    let attempts = 0;
    const maxAttempts = 20;
    
    const pollValidation = async () => {
        attempts++;
        
        try {
            const result = await checkValidationBySessionId(sessionId);
            
            if (result.found) {
                if (result.match_found) {
                    console.log('✅ Validation successful');
                    showSuccessScreen({
                        ...result,
                        livenessConfidence: livenessConfidence,
                        sessionId: sessionId,
                        validationType: 'AWS_FACE_LIVENESS'
                    });
                    return;
                } else {
                    handleValidationFailure(result);
                    return;
                }
            }
            
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000);
            } else {
                showStatus('livenessStatus', '❌ Tiempo de validación agotado', 'error');
                showRetryButton();
            }
            
        } catch (error) {
            console.error('Validation polling error:', error);
            
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000);
            } else {
                showStatus('livenessStatus', '❌ Error en la validación', 'error');
                showRetryButton();
            }
        }
    };
    
    setTimeout(pollValidation, 3000);
}

async function checkValidationBySessionId(sessionId) {
    try {
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
        console.error('Error checking validation:', error);
        throw error;
    }
}

function handleValidationFailure(result) {
    console.log(`❌ Validation failed: ${result.status}`);
    
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
        default:
            errorMessage = '❌ Error en la validación biométrica';
    }
    
    showStatus('livenessStatus', errorMessage, 'error');
    showRetryButton();
}

// ============================================
// SUCCESS SCREEN
// ============================================

function showSuccessScreen(validationResult) {
    const personNameElement = document.getElementById('personName');
    const documentNumberElement = document.getElementById('documentNumberDisplay');
    const cellNumberElement = document.getElementById('cellNumberDisplay');
    const livenessConfidenceElement = document.getElementById('livenessConfidence');
    const sessionIdElement = document.getElementById('sessionIdDisplay');
    
    if (!personNameElement || !documentNumberElement || !cellNumberElement) {
        console.error('Success screen elements not found');
        return;
    }
    
    const personName = validationResult.person_name || formData.personName || 'USUARIO VERIFICADO';
    personNameElement.textContent = personName.toUpperCase();
    
    documentNumberElement.textContent = formData.numeroDocumento;
    cellNumberElement.textContent = formData.numeroCelular;
    
    // Display REAL liveness information
    if (livenessConfidenceElement) {
        livenessConfidenceElement.textContent = `${validationResult.livenessConfidence?.toFixed(1) || 0}%`;
    }
    
    if (sessionIdElement) {
        sessionIdElement.textContent = validationResult.sessionId?.substring(0, 12) + '...' || 'N/A';
    }
    
    console.log('✅ Identity verified using REAL AWS Face Liveness');
    console.log(`   Session ID: ${validationResult.sessionId}`);
    console.log(`   Liveness Confidence: ${validationResult.livenessConfidence}%`);
    console.log(`   Similarity Score: ${validationResult.similarity}%`);
    
    showInterface('interfaceSuccess');
}

// ============================================
// UTILITY FUNCTIONS (SAME AS BEFORE)
// ============================================

function showInterface(interfaceId) {
    document.querySelectorAll('.interface').forEach(iface => {
        iface.classList.remove('active');
    });
    
    const targetInterface = document.getElementById(interfaceId);
    if (targetInterface) {
        targetInterface.classList.add('active');
    }
    
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
    
    if (type !== 'error') {
        setTimeout(() => {
            element.classList.add('hidden');
        }, 5000);
    }
}

function showRetryButton() {
    const retryButton = document.getElementById('retryLiveness');
    if (retryButton) {
        retryButton.style.display = 'inline-block';
    }
}

function retryLivenessProcess() {
    livenessSessionId = null;
    processingInProgress = false;
    
    const retryButton = document.getElementById('retryLiveness');
    if (retryButton) {
        retryButton.style.display = 'none';
    }
    
    const statusElement = document.getElementById('livenessStatus');
    if (statusElement) {
        statusElement.classList.add('hidden');
    }
    
    startRealFaceLiveness();
}

// ============================================
// CAMERA FUNCTIONS (SAME AS BEFORE)
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
// API FUNCTIONS (SAME AS BEFORE)
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
                startRealFaceLiveness(); // ✅ REAL FUNCTION CALL
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
            
            // Store form data
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
                            permissionText.textContent = 'Documento encontrado en el sistema. Para completar la verificación biométrica, necesitamos acceso a su cámara web para AWS Face Liveness.';
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
                startRealFaceLiveness(); // ✅ REAL FUNCTION CALL
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
            resetToInitialState();
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
    
    // Interface 3 - Back button
    const atrasLiveness = document.getElementById('atrasLiveness');
    if (atrasLiveness) {
        atrasLiveness.addEventListener('click', function() {
            // Clean up liveness session
            if (livenessSessionId) {
                console.log('🔄 Cleaning up liveness session on back navigation');
                livenessSessionId = null;
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
            resetToInitialState();
        });
    }
    
    // Success interface - Pagar button
    const pagarBtn = document.getElementById('pagarBtn');
    if (pagarBtn) {
        pagarBtn.addEventListener('click', function() {
            console.log('Continue process button clicked');
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

function resetToInitialState() {
    // Reset form data
    formData = {
        tipoDocumento: '',
        numeroDocumento: '',
        numeroCelular: '',
        documentExists: false
    };
    
    processingInProgress = false;
    
    // Reset liveness state
    livenessSessionId = null;
    
    // Reset form
    const documentForm = document.getElementById('documentForm');
    if (documentForm) documentForm.reset();
    
    // Stop camera
    stopCamera();
    
    // Hide retry button
    const retryButton = document.getElementById('retryLiveness');
    if (retryButton) {
        retryButton.style.display = 'none';
    }
    
    // Hide status
    const statusElement = document.getElementById('livenessStatus');
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
    
    // ✅ CORRECTED: Check for required libraries for REAL Face Liveness
    if (typeof window.Amplify === 'undefined') {
        console.error('❌ AWS Amplify not loaded');
        showError('Error: AWS Amplify no está disponible. Verifique la conexión a internet.');
        return;
    }
    
    if (typeof window.AmplifyUIReact === 'undefined') {
        console.error('❌ AWS Amplify UI React not loaded');
        showError('Error: Componente AWS Face Liveness no está disponible.');
        return;
    }
    
    if (typeof window.AmplifyUIReact.FaceLivenessDetector === 'undefined') {
        console.error('❌ FaceLivenessDetector component not found');
        showError('Error: FaceLivenessDetector no está disponible.');
        return;
    }
    
    if (typeof React === 'undefined' || typeof ReactDOM === 'undefined') {
        console.error('❌ React not loaded');
        showError('Error: React no está disponible.');
        return;
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
    console.log('   - AWS Amplify:', typeof window.Amplify !== 'undefined' ? 'Available' : 'Missing');
    console.log('   - Amplify UI React:', typeof window.AmplifyUIReact !== 'undefined' ? 'Available' : 'Missing');
    console.log('   - FaceLivenessDetector:', typeof window.AmplifyUIReact?.FaceLivenessDetector !== 'undefined' ? 'Available' : 'Missing');
    console.log('   - React:', typeof React !== 'undefined' ? 'Available' : 'Missing');
    
    console.log('✅ Rekognition POC Frontend initialized with REAL AWS Face Liveness');
}

// ============================================
// START APPLICATION
// ============================================

document.addEventListener('DOMContentLoaded', initializeApp);

window.addEventListener('beforeunload', function() {
    stopCamera();
    
    // Cleanup liveness session
    if (livenessSessionId) {
        console.log('🔄 Cleaning up liveness session on page unload');
        livenessSessionId = null;
    }
});

console.log('✅ REAL AWS Face Liveness integration loaded - Production ready!');