// ============================================
// GLOBAL VARIABLES & CONFIG
// ============================================

// API Base URL will be set from config.js
let API_BASE_URL = '';

let currentStream = null;
let formData = {
    tipoDocumento: '',
    numeroDocumento: '',
    numeroCelular: ''
};

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
}

function showError(message) {
    const errorModal = document.getElementById('errorModal');
    const errorMessage = document.getElementById('errorMessage');
    
    errorMessage.textContent = message;
    errorModal.classList.remove('hidden');
}

function hideError() {
    document.getElementById('errorModal').classList.add('hidden');
}

function showSpinner(buttonId) {
    const button = document.getElementById(buttonId);
    const span = button.querySelector('span');
    const spinner = button.querySelector('.spinner');
    
    if (span) span.style.display = 'none';
    if (spinner) spinner.classList.remove('hidden');
    button.disabled = true;
}

function hideSpinner(buttonId) {
    const button = document.getElementById(buttonId);
    const span = button.querySelector('span');
    const spinner = button.querySelector('.spinner');
    
    if (span) span.style.display = 'inline';
    if (spinner) spinner.classList.add('hidden');
    button.disabled = false;
}

function showStatus(elementId, message, type = 'info') {
    const element = document.getElementById(elementId);
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
// 🆕 IMPROVED CAMERA FUNCTIONS
// ============================================

function checkCameraSupport() {
    /**
     * Verificar si el navegador soporta cámara y está en contexto seguro
     */
    
    // 1. Verificar si estamos en contexto seguro (HTTPS o localhost)
    const isSecureContext = window.isSecureContext || 
                           location.protocol === 'https:' || 
                           location.hostname === 'localhost' ||
                           location.hostname === '127.0.0.1';
    
    // 2. Verificar si getUserMedia está disponible
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
        
        // 🆕 VERIFICACIÓN MEJORADA
        const cameraSupport = checkCameraSupport();
        
        if (!cameraSupport.isSupported) {
            let errorMessage = 'No se puede acceder a la cámara. ';
            
            if (!cameraSupport.isSecureContext) {
                errorMessage += 'Este sitio requiere HTTPS para acceder a la cámara. ';
                errorMessage += 'Por favor, asegúrate de estar usando una conexión segura (HTTPS).';
            } else if (!cameraSupport.hasGetUserMedia) {
                errorMessage += 'Tu navegador no soporta acceso a cámara web. ';
                errorMessage += 'Por favor, usa un navegador moderno como Chrome, Firefox o Safari.';
            } else {
                errorMessage += 'Configuración de seguridad no compatible.';
            }
            
            throw new Error(errorMessage);
        }
        
        // Stop existing stream
        if (currentStream) {
            currentStream.getTracks().forEach(track => track.stop());
        }
        
        // Request camera permission and start stream
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
        
        // 🆕 MANEJO MEJORADO DE ERRORES
        if (error.message.includes('HTTPS') || error.message.includes('conexión segura')) {
            // Error de HTTPS - mensaje personalizado ya incluido
            errorMessage = error.message;
        } else if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            errorMessage += 'Permisos de cámara denegados. Por favor, permite el acceso a la cámara en tu navegador y recarga la página.';
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
            errorMessage += 'No se encontró ninguna cámara en tu dispositivo. Verifica que esté conectada correctamente.';
        } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
            errorMessage += 'La cámara está siendo usada por otra aplicación. Cierra otras apps que puedan estar usando la cámara.';
        } else if (error.name === 'OverconstrainedError' || error.name === 'ConstraintNotSatisfiedError') {
            errorMessage += 'Configuración de cámara no soportada. Intentando con configuración básica...';
            
            // 🆕 FALLBACK: Intentar con configuración más simple
            try {
                if (currentStream) {
                    currentStream.getTracks().forEach(track => track.stop());
                }
                
                currentStream = await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: false
                });
                
                video.srcObject = currentStream;
                return true;
                
            } catch (fallbackError) {
                errorMessage += ' La configuración alternativa también falló.';
            }
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
    const context = canvas.getContext('2d');
    
    // Set canvas dimensions to match video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // Draw current video frame to canvas
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Convert to blob
    return new Promise(resolve => {
        canvas.toBlob(resolve, 'image/jpeg', 0.8);
    });
}

// ============================================
// API FUNCTIONS (Sin cambios significativos)
// ============================================

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

// ============================================
// DOCUMENT PROCESSING (Sin cambios)
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
        
        // Index document
        showStatus('documentStatus', 'Procesando documento...', 'info');
        const indexResult = await indexDocument(fileName);
        
        if (indexResult.success) {
            showStatus('documentStatus', '✅ Documento procesado exitosamente', 'success');
            
            // Store person name for later use
            if (indexResult.person_name) {
                formData.personName = indexResult.person_name;
            }
            
            // Wait a moment then proceed to user photo
            setTimeout(() => {
                stopCamera();
                showInterface('interface3');
                startCamera('videoUser');
            }, 2000);
            
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
// USER PHOTO PROCESSING (Sin cambios)
// ============================================

async function processUserPhoto() {
    try {
        showSpinner('tomarFotoUsuario');
        
        // Capture photo
        const imageBlob = await capturePhoto('videoUser', 'canvasUser');
        
        if (!imageBlob) {
            throw new Error('No se pudo capturar la imagen');
        }
        
        // Generate filename with timestamp
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const fileName = `${formData.numeroDocumento}-user-${timestamp}.jpg`;
        
        // Get presigned URL
        showStatus('userStatus', 'Preparando upload...', 'info');
        const uploadData = await getPresignedUrl(fileName, 'user-photos');
        
        // Upload to S3
        showStatus('userStatus', 'Subiendo foto...', 'info');
        await uploadToS3(imageBlob, uploadData.uploadUrl);
        
        showStatus('userStatus', '✅ Foto subida exitosamente', 'success');
        
        // Start validation polling
        startValidationPolling();
        
    } catch (error) {
        console.error('User photo processing error:', error);
        showStatus('userStatus', `❌ ${error.message}`, 'error');
    } finally {
        hideSpinner('tomarFotoUsuario');
    }
}

// ============================================
// VALIDATION POLLING (Sin cambios)
// ============================================

function startValidationPolling() {
    const progressElement = document.getElementById('validationProgress');
    const timerElement = document.getElementById('progressTimer');
    
    progressElement.classList.remove('hidden');
    
    let attempts = 0;
    const maxAttempts = 5; // 10 seconds total (5 attempts x 2 seconds)
    let timeLeft = 10;
    
    // Update timer display
    const timerInterval = setInterval(() => {
        timeLeft--;
        timerElement.textContent = timeLeft;
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
        }
    }, 1000);
    
    // Polling function
    const pollValidation = async () => {
        attempts++;
        
        try {
            const result = await checkValidation(formData.numeroDocumento);
            
            if (result.match_found) {
                // SUCCESS - Match found!
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                stopCamera();
                showSuccessScreen(result);
                return;
            }
            
            // Continue polling if not reached max attempts
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000); // Wait 2 seconds before next attempt
            } else {
                // Max attempts reached - no match found
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                showStatus('userStatus', '❌ No se encontró coincidencia con el documento', 'error');
            }
            
        } catch (error) {
            console.error('Validation polling error:', error);
            
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000); // Retry on error
            } else {
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                showStatus('userStatus', '❌ Error verificando la validación', 'error');
            }
        }
    };
    
    // Start polling after 3 seconds (give time for processing)
    setTimeout(pollValidation, 3000);
}

// ============================================
// SUCCESS SCREEN (Sin cambios)
// ============================================

function showSuccessScreen(validationResult) {
    // Update success screen with data
    const personNameElement = document.getElementById('personName');
    const documentNumberElement = document.getElementById('documentNumberDisplay');
    const cellNumberElement = document.getElementById('cellNumberDisplay');
    
    // Use person name from validation result or form data
    const personName = validationResult.person_name || formData.personName || 'USUARIO VERIFICADO';
    personNameElement.textContent = personName.toUpperCase();
    
    documentNumberElement.textContent = formData.numeroDocumento;
    cellNumberElement.textContent = formData.numeroCelular;
    
    // Show success interface
    showInterface('interfaceSuccess');
}

// ============================================
// 🆕 IMPROVED INITIALIZATION
// ============================================

function checkSystemCompatibility() {
    /**
     * Verificar compatibilidad del sistema antes de inicializar
     */
    
    const issues = [];
    
    // Verificar soporte de cámara
    const cameraSupport = checkCameraSupport();
    if (!cameraSupport.isSupported) {
        if (!cameraSupport.isSecureContext) {
            issues.push('🔒 Conexión no segura: Se requiere HTTPS para usar la cámara');
        }
        if (!cameraSupport.hasGetUserMedia) {
            issues.push('📱 Navegador incompatible: No soporta acceso a cámara web');
        }
    }
    
    // Verificar API Gateway URL
    if (!API_BASE_URL || API_BASE_URL === 'YOUR_API_GATEWAY_URL_HERE') {
        issues.push('⚙️ Configuración pendiente: URL del API Gateway no configurada');
    }
    
    // Verificar APIs básicas
    if (!window.fetch) {
        issues.push('🌐 Navegador muy antiguo: No soporta fetch API');
    }
    
    return issues;
}

// ============================================
// EVENT LISTENERS (Sin cambios significativos)
// ============================================

function setupEventListeners() {
    // Interface 1 - Form submission
    document.getElementById('documentForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Validate form
        const tipoDocumento = document.getElementById('tipoDocumento').value;
        const numeroDocumento = document.getElementById('numeroDocumento').value.trim();
        const numeroCelular = document.getElementById('numeroCelular').value.trim();
        
        if (!tipoDocumento || !numeroDocumento || !numeroCelular) {
            showError('Por favor complete todos los campos obligatorios');
            return;
        }
        
        // Store form data
        formData = {
            tipoDocumento,
            numeroDocumento,
            numeroCelular
        };
        
        // Show permission interface
        showInterface('interfacePermission');
    });
    
    // Permission interface - Allow camera
    document.getElementById('permitirCamara').addEventListener('click', async function() {
        showSpinner('permitirCamara');
        
        const cameraStarted = await startCamera('videoDocument');
        
        hideSpinner('permitirCamara');
        
        if (cameraStarted) {
            // Update document type display
            document.getElementById('tipoDocumentoDisplay').textContent = formData.tipoDocumento;
            showInterface('interface2');
        }
    });
    
    // Permission interface - Back button
    document.getElementById('atrasPermission').addEventListener('click', function() {
        showInterface('interface1');
    });
    
    // Interface 2 - Take document photo
    document.getElementById('tomarFotoDocumento').addEventListener('click', processDocumentPhoto);
    
    // Interface 2 - Back button
    document.getElementById('atrasDocumento').addEventListener('click', function() {
        stopCamera();
        showInterface('interfacePermission');
    });
    
    // Interface 3 - Take user photo
    document.getElementById('tomarFotoUsuario').addEventListener('click', processUserPhoto);
    
    // Interface 3 - Back button
    document.getElementById('atrasUsuario').addEventListener('click', function() {
        stopCamera();
        showInterface('interface2');
        startCamera('videoDocument');
    });
    
    // Success interface - Finalizar button (back to start)
    document.getElementById('finalizarBtn').addEventListener('click', function() {
        // Reset form data
        formData = {};
        
        // Reset form
        document.getElementById('documentForm').reset();
        
        // Show initial interface
        showInterface('interface1');
    });
    
    // Success interface - Pagar button (no functionality as requested)
    document.getElementById('pagarBtn').addEventListener('click', function() {
        // No functionality as per requirements
        console.log('Pagar button clicked - no functionality implemented');
    });
    
    // Error modal - Close button
    document.getElementById('closeErrorModal').addEventListener('click', hideError);
    
    // Close modal when clicking outside
    document.getElementById('errorModal').addEventListener('click', function(e) {
        if (e.target === this) {
            hideError();
        }
    });
}

// ============================================
// 🆕 IMPROVED INITIALIZATION
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
    
    // 🆕 VERIFICAR COMPATIBILIDAD DEL SISTEMA
    const compatibilityIssues = checkSystemCompatibility();
    
    if (compatibilityIssues.length > 0) {
        console.warn('⚠️  System compatibility issues detected:');
        compatibilityIssues.forEach(issue => console.warn('   -', issue));
        
        // Mostrar advertencias pero no bloquear la app
        if (compatibilityIssues.some(issue => issue.includes('HTTPS'))) {
            console.error('🔒 HTTPS Required: Camera access requires secure connection');
        }
    }
    
    // Setup event listeners
    setupEventListeners();
    
    // Show initial interface
    showInterface('interface1');
    
    // 🆕 Log información del entorno
    console.log('🔧 Environment Info:');
    console.log('   - Protocol:', location.protocol);
    console.log('   - Host:', location.host);
    console.log('   - Secure Context:', window.isSecureContext);
    console.log('   - Camera Support:', checkCameraSupport().isSupported);
    
    console.log('✅ Rekognition POC Frontend initialized');
}

// ============================================
// START APPLICATION
// ============================================

document.addEventListener('DOMContentLoaded', initializeApp);

// Cleanup camera stream when page unloads
window.addEventListener('beforeunload', function() {
    stopCamera();
});