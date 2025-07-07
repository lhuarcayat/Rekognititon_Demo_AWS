// ============================================
// GLOBAL VARIABLES & CONFIG
// ============================================

// API Base URL will be set from config.js
let API_BASE_URL = '';

let currentStream = null;
let userPhotoTimer = null; // 🆕 Timer para foto de rostro
let formData = {
    tipoDocumento: '',
    numeroDocumento: '',
    numeroCelular: '',
    documentExists: false // 🆕 Flag para documento existente
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
    
    // 🆕 Limpiar timer al cambiar de interfaz
    if (userPhotoTimer) {
        clearTimeout(userPhotoTimer);
        userPhotoTimer = null;
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
    const context = canvas.getContext('2d');
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    return new Promise(resolve => {
        canvas.toBlob(resolve, 'image/jpeg', 0.8);
    });
}

// ============================================
// 🆕 API FUNCTIONS - UPDATED
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

// ============================================
// 🆕 DOCUMENT PROCESSING - UPDATED
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
        
        // 🆕 Index document WITH IMMEDIATE FACE DETECTION
        showStatus('documentStatus', 'Validando documento...', 'info');
        const indexResult = await indexDocument(fileName);
        
        if (indexResult.success) {
            showStatus('documentStatus', '✅ Documento validado exitosamente', 'success');
            
            // Store person name for later use
            if (indexResult.person_name) {
                formData.personName = indexResult.person_name;
            }
            
            // Wait a moment then proceed to user photo
            setTimeout(() => {
                stopCamera();
                showInterface('interface3');
                startUserPhotoInterface();
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
// 🆕 USER PHOTO PROCESSING - UPDATED WITH TIMER
// ============================================

function startUserPhotoInterface() {
    startCamera('videoUser');
    
    // 🆕 INICIAR TIMER DE 1 MINUTO
    console.log('🕐 Starting 1-minute timer for user photo...');
    
    let timeLeft = 60; // 60 segundos
    
    // Mostrar timer en la interfaz si existe
    const timerElement = document.getElementById('userPhotoTimer');
    if (timerElement) {
        timerElement.textContent = `${timeLeft}s`;
        timerElement.classList.remove('hidden');
    }
    
    // Actualizar timer cada segundo
    const timerInterval = setInterval(() => {
        timeLeft--;
        
        if (timerElement) {
            timerElement.textContent = `${timeLeft}s`;
            
            // Cambiar color cuando queden 10 segundos
            if (timeLeft <= 10) {
                timerElement.style.color = '#dc2626'; // Rojo
            }
        }
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            handleUserPhotoTimeout();
        }
    }, 1000);
    
    // Guardar referencias para limpieza
    userPhotoTimer = {
        interval: timerInterval,
        cleanup: () => {
            clearInterval(timerInterval);
            if (timerElement) {
                timerElement.classList.add('hidden');
                timerElement.style.color = ''; // Reset color
            }
        }
    };
}

function handleUserPhotoTimeout() {
    console.log('⏰ User photo timer expired - cleaning up...');
    
    // Limpiar timer
    if (userPhotoTimer) {
        userPhotoTimer.cleanup();
        userPhotoTimer = null;
    }
    
    // Parar cámara
    stopCamera();
    
    // 🆕 CLEANUP: Borrar documento si es usuario nuevo
    if (!formData.documentExists) {
        cleanupDocumentOnTimeout();
    }
    
    // Mostrar error y volver a interface1
    showError('Tiempo agotado para tomar la foto de rostro. Por favor, inicia el proceso nuevamente.');
    
    setTimeout(() => {
        hideError();
        resetToInitialState();
    }, 3000);
}

async function cleanupDocumentOnTimeout() {
    try {
        // 🆕 IMPLEMENTAR CLEANUP API
        const response = await fetch(`${API_BASE_URL}/cleanup-document`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                tipoDocumento: formData.tipoDocumento,
                numeroDocumento: formData.numeroDocumento,
                reason: 'TIMEOUT'
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log(`✅ Document cleanup successful: ${result.message}`);
        } else {
            console.error(`❌ Document cleanup failed: ${result.error}`);
        }
        
    } catch (error) {
        console.error('Error cleaning up document on timeout:', error);
    }
}

async function processUserPhoto() {
    try {
        // 🆕 Limpiar timer al tomar foto exitosamente
        if (userPhotoTimer) {
            userPhotoTimer.cleanup();
            userPhotoTimer = null;
        }
        
        showSpinner('tomarFotoUsuario');
        
        // Capture photo
        const imageBlob = await capturePhoto('videoUser', 'canvasUser');
        
        if (!imageBlob) {
            throw new Error('No se pudo capturar la imagen');
        }
        
        // 🆕 NUEVO NAMING PATTERN: {tipoDocumento}-{numeroDocumento}-user-{timestamp}
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const fileName = `${formData.tipoDocumento}-${formData.numeroDocumento}-user-${timestamp}.jpg`;
        
        console.log(`📸 Generated user photo filename: ${fileName}`);
        
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
// VALIDATION POLLING (Sin cambios significativos)
// ============================================

function startValidationPolling() {
    const progressElement = document.getElementById('validationProgress');
    const timerElement = document.getElementById('progressTimer');
    
    progressElement.classList.remove('hidden');
    
    let attempts = 0;
    const maxAttempts = 5;
    let timeLeft = 10;
    
    const timerInterval = setInterval(() => {
        timeLeft--;
        timerElement.textContent = timeLeft;
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
        }
    }, 1000);
    
    const pollValidation = async () => {
        attempts++;
        
        try {
            const result = await checkValidation(formData.numeroDocumento);
            
            if (result.match_found) {
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                stopCamera();
                showSuccessScreen(result);
                return;
            }
            
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000);
            } else {
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                showStatus('userStatus', '❌ No se encontró coincidencia con el documento', 'error');
            }
            
        } catch (error) {
            console.error('Validation polling error:', error);
            
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 2000);
            } else {
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                showStatus('userStatus', '❌ Error verificando la validación', 'error');
            }
        }
    };
    
    setTimeout(pollValidation, 3000);
}

// ============================================
// SUCCESS SCREEN (Sin cambios)
// ============================================

function showSuccessScreen(validationResult) {
    const personNameElement = document.getElementById('personName');
    const documentNumberElement = document.getElementById('documentNumberDisplay');
    const cellNumberElement = document.getElementById('cellNumberDisplay');
    
    const personName = validationResult.person_name || formData.personName || 'USUARIO VERIFICADO';
    personNameElement.textContent = personName.toUpperCase();
    
    documentNumberElement.textContent = formData.numeroDocumento;
    cellNumberElement.textContent = formData.numeroCelular;
    
    showInterface('interfaceSuccess');
}

// ============================================
// 🆕 UTILITY FUNCTIONS
// ============================================

function resetToInitialState() {
    // Reset form data
    formData = {
        tipoDocumento: '',
        numeroDocumento: '',
        numeroCelular: '',
        documentExists: false
    };
    
    // Reset form
    document.getElementById('documentForm').reset();
    
    // Limpiar timers
    if (userPhotoTimer) {
        userPhotoTimer.cleanup();
        userPhotoTimer = null;
    }
    
    // Stop camera
    stopCamera();
    
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
    
    return issues;
}

// ============================================
// 🆕 EVENT LISTENERS - UPDATED
// ============================================

function setupEventListeners() {
    // 🆕 Interface 1 - Form submission WITH DOCUMENT CHECK
    document.getElementById('documentForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // Validate form
        const tipoDocumento = document.getElementById('tipoDocumento').value;
        const numeroDocumento = document.getElementById('numeroDocumento').value.trim();
        const numeroCelular = document.getElementById('numeroCelular').value.trim();
        
        if (!tipoDocumento || !numeroDocumento || !numeroCelular) {
            showError('Por favor complete todos los campos obligatorios');
            return;
        }
        
        // Store basic form data
        formData.tipoDocumento = tipoDocumento;
        formData.numeroDocumento = numeroDocumento;
        formData.numeroCelular = numeroCelular;
        
        // 🆕 CHECK IF DOCUMENT EXISTS
        try {
            showSpinner('documentForm').querySelector('button[type="submit"]');
            
            console.log(`🔍 Checking if document exists: ${tipoDocumento}-${numeroDocumento}`);
            
            const documentCheck = await checkDocumentExists(tipoDocumento, numeroDocumento);
            
            formData.documentExists = documentCheck.exists;
            
            if (documentCheck.exists) {
                // 🆕 USUARIO EXISTENTE - Saltar a verification
                console.log('✅ Existing user - skipping document capture');
                
                hideSpinner('documentForm').querySelector('button[type="submit"]');
                
                // Mostrar mensaje y ir directo a interface3
                showStatus('documentStatus', '✅ ' + documentCheck.message, 'success');
                
                setTimeout(() => {
                    showInterface('interfacePermission');
                    
                    // Actualizar texto para usuario existente
                    const permissionText = document.querySelector('.permission-content p');
                    if (permissionText) {
                        permissionText.textContent = 'Documento encontrado en el sistema. Para completar la verificación biométrica, necesitamos acceso a su cámara web para validar su identidad.';
                    }
                }, 1000);
            } else {
                // 🆕 USUARIO NUEVO - Proceso completo
                console.log('🆕 New user - full registration required');
                
                hideSpinner('documentForm').querySelector('button[type="submit"]');
                showInterface('interfacePermission');
            }
            
        } catch (error) {
            console.error('Error checking document existence:', error);
            hideSpinner('documentForm').querySelector('button[type="submit"]');
            showError('Error verificando el documento. Por favor, intente nuevamente.');
        }
    });
    
    // Permission interface - Allow camera
    document.getElementById('permitirCamara').addEventListener('click', async function() {
        showSpinner('permitirCamara');
        
        if (formData.documentExists) {
            // 🆕 USUARIO EXISTENTE - Ir directo a interface3
            const cameraStarted = await startCamera('videoUser');
            
            hideSpinner('permitirCamara');
            
            if (cameraStarted) {
                showInterface('interface3');
                startUserPhotoInterface();
            }
        } else {
            // 🆕 USUARIO NUEVO - Ir a interface2 primero
            const cameraStarted = await startCamera('videoDocument');
            
            hideSpinner('permitirCamara');
            
            if (cameraStarted) {
                document.getElementById('tipoDocumentoDisplay').textContent = formData.tipoDocumento;
                showInterface('interface2');
            }
        }
    });
    
    // Permission interface - Back button
    document.getElementById('atrasPermission').addEventListener('click', function() {
        resetToInitialState();
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
        // Limpiar timer
        if (userPhotoTimer) {
            userPhotoTimer.cleanup();
            userPhotoTimer = null;
        }
        
        stopCamera();
        
        if (formData.documentExists) {
            // Usuario existente vuelve a permissions
            showInterface('interfacePermission');
        } else {
            // Usuario nuevo vuelve a interface2
            showInterface('interface2');
            startCamera('videoDocument');
        }
    });
    
    // Success interface - Finalizar button
    document.getElementById('finalizarBtn').addEventListener('click', function() {
        resetToInitialState();
    });
    
    // Success interface - Pagar button
    document.getElementById('pagarBtn').addEventListener('click', function() {
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
    
    console.log('✅ Rekognition POC Frontend initialized with new flow');
}

// ============================================
// START APPLICATION
// ============================================

document.addEventListener('DOMContentLoaded', initializeApp);

window.addEventListener('beforeunload', function() {
    stopCamera();
    
    // Limpiar timers
    if (userPhotoTimer) {
        userPhotoTimer.cleanup();
    }
});