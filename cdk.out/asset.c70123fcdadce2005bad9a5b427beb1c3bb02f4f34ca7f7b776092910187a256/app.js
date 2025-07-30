// ============================================
// GLOBAL VARIABLES & CONFIG
// ============================================

// API Base URL will be set from config.js
let API_BASE_URL = '';

let currentStream = null;
let userPhotoTimer = null; // 🆕 Timer para foto de rostro
let processingInProgress = false; // 🆕 Flag de proceso protegido
let attemptNumber = 0; // 🆕 Contador de intentos
let formData = {
    tipoDocumento: '',
    numeroDocumento: '',
    numeroCelular: '',
    documentExists: false
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
    
    // Reset attempt counter cuando cambias de interfaz
    attemptNumber = 0;
    processingInProgress = false;
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
        
        // Index document WITH IMMEDIATE FACE DETECTION
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
// 🆕 USER PHOTO PROCESSING - COMPLETAMENTE NUEVO
// ============================================

function startUserPhotoInterface() {
    startCamera('videoUser');
    
    // 🆕 RESET ATTEMPT COUNTER
    attemptNumber = 0;
    processingInProgress = false;
    
    // 🆕 INICIAR TIMER DE 30 SEGUNDOS con PROCESO PROTEGIDO
    console.log('🕐 Starting 30-second timer for user photo...');
    
    let timeLeft = 30;
    
    // Mostrar timer en la interfaz
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
        
        // 🆕 VERIFICAR SI HAY PROCESO EN CURSO
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            
            if (processingInProgress) {
                console.log('⏰ Timer expired but process in progress - waiting for completion...');
                // NO hacer nada, dejar que el proceso termine
            } else {
                console.log('⏰ Timer expired and no process active - cleaning up...');
                handleUserPhotoTimeout();
            }
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

// 🆕 NUEVA FUNCIÓN PRINCIPAL DE VALIDACIÓN CON REINTENTOS
async function processUserPhoto() {
    // 🆕 MARCAR PROCESO COMO ACTIVO
    processingInProgress = true;
    
    try {
        // 🆕 INCREMENT ATTEMPT NUMBER
        attemptNumber++;
        
        console.log(`🔄 Starting user photo validation attempt #${attemptNumber}`);
        
        showSpinner('tomarFotoUsuario');
        
        // Capture photo
        const imageBlob = await capturePhoto('videoUser', 'canvasUser');
        
        if (!imageBlob) {
            throw new Error('No se pudo capturar la imagen');
        }
        
        // 🆕 NUEVO NAMING PATTERN CON ATTEMPT NUMBER
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const fileName = `${formData.tipoDocumento}-${formData.numeroDocumento}-user-${timestamp}-attempt-${attemptNumber}.jpg`;
        
        console.log(`📸 Generated user photo filename: ${fileName}`);
        
        // Get presigned URL
        showStatus('userStatus', 'Preparando upload...', 'info');
        const uploadData = await getPresignedUrl(fileName, 'user-photos');
        
        // Upload to S3
        showStatus('userStatus', 'Subiendo foto...', 'info');
        await uploadToS3(imageBlob, uploadData.uploadUrl);
        
        showStatus('userStatus', '✅ Foto subida exitosamente', 'success');
        
        // 🆕 EMPEZAR POLLING ESPECÍFICO PARA ESTA TENTATIVA
        await startValidationPollingWithRetry(fileName);
        
    } catch (error) {
        console.error('User photo processing error:', error);
        showStatus('userStatus', `❌ ${error.message}`, 'error');
        
        // 🆕 MOSTRAR BOTÓN DE REINTENTO
        showRetryButton('Error capturando foto de usuario');
        
    } finally {
        hideSpinner('tomarFotoUsuario');
        // 🆕 MARCAR PROCESO COMO COMPLETADO
        processingInProgress = false;
    }
}

// 🆕 FUNCIÓN DE POLLING CON MANEJO DE ERRORES ESPECÍFICOS
async function startValidationPollingWithRetry(userPhotoKey) {
    const progressElement = document.getElementById('validationProgress');
    const timerElement = document.getElementById('progressTimer');
    
    progressElement.classList.remove('hidden');
    
    let attempts = 0;
    const maxAttempts = 10; // Más intentos para dar tiempo al backend
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
            // 🆕 BUSCAR RESULTADO ESPECÍFICO PARA ESTE ARCHIVO
            const result = await checkValidationByPhotoKey(userPhotoKey);
            
            if (result.found) {
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                
                if (result.match_found) {
                    // 🆕 ÉXITO - Limpiar timer completamente
                    if (userPhotoTimer) {
                        userPhotoTimer.cleanup();
                        userPhotoTimer = null;
                    }
                    
                    stopCamera();
                    showSuccessScreen(result);
                    return;
                } else {
                    // 🆕 FALLO - Mostrar error específico y botón de reintento
                    handleValidationFailure(result);
                    return;
                }
            }
            
            // Sin resultado aún, continuar polling
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 1000);
            } else {
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                showRetryButton('Tiempo de espera agotado para la validación');
            }
            
        } catch (error) {
            console.error('Validation polling error:', error);
            
            if (attempts < maxAttempts) {
                setTimeout(pollValidation, 1000);
            } else {
                clearInterval(timerInterval);
                progressElement.classList.add('hidden');
                showRetryButton('Error verificando la validación');
            }
        }
    };
    
    // Empezar polling después de 2 segundos
    setTimeout(pollValidation, 2000);
}

// 🆕 FUNCIÓN PARA BUSCAR VALIDACIÓN POR FOTO ESPECÍFICA
async function checkValidationByPhotoKey(userPhotoKey) {
    try {
        // Extraer número de documento del nombre del archivo
        const numeroDocumento = formData.numeroDocumento;
        
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
        
        // 🆕 VERIFICAR SI EL RESULTADO CORRESPONDE A ESTA FOTO ESPECÍFICA
        if (result.user_image_key && result.user_image_key.includes(userPhotoKey.split('-attempt-')[0])) {
            return {
                found: true,
                match_found: result.match_found,
                status: result.status,
                error_type: result.error_type,
                allow_retry: result.allow_retry,
                ...result
            };
        }
        
        return { found: false };
        
    } catch (error) {
        console.error('Error checking validation by photo key:', error);
        throw error;
    }
}

// 🆕 MANEJAR FALLO DE VALIDACIÓN CON ERRORES ESPECÍFICOS
function handleValidationFailure(result) {
    console.log(`❌ Validation failed: ${result.status} - ${result.error_type}`);
    
    let errorMessage = '';
    
    // 🆕 MENSAJES ESPECÍFICOS SEGÚN TIPO DE ERROR
    switch (result.error_type) {
        case 'NO_FACE_DETECTED':
            errorMessage = '❌ No se detectó rostro, intente nuevamente...';
            break;
        case 'NO_MATCH_FOUND':
            errorMessage = '❌ Rostro no coincide, intente nuevamente...';
            break;
        case 'LOW_CONFIDENCE':
            errorMessage = '❌ Coincidencia de baja confianza, intente nuevamente...';
            break;
        default:
            errorMessage = '❌ Error en la validación, intente nuevamente...';
    }
    
    // Mostrar error específico
    showStatus('userStatus', errorMessage, 'error');
    
    // 🆕 DECIDIR SI PERMITIR REINTENTO O VOLVER AL INICIO
    if (result.allow_retry !== false) {
        showRetryButton(errorMessage);
    } else {
        // Fallo crítico - limpiar y volver al inicio
        setTimeout(() => {
            handleCriticalFailure();
        }, 3000);
    }
}

// 🆕 MOSTRAR BOTÓN DE REINTENTO
function showRetryButton(message) {
    // Ocultar spinner del botón principal
    hideSpinner('tomarFotoUsuario');
    
    // Mostrar mensaje de error
    showStatus('userStatus', message, 'error');
    
    // 🆕 VERIFICAR SI EL TIMER AÚN ESTÁ ACTIVO
    if (!userPhotoTimer) {
        // Timer ya expiró, ir a cleanup
        handleCriticalFailure();
        return;
    }
    
    // Cambiar texto del botón principal
    const button = document.getElementById('tomarFotoUsuario');
    const span = button.querySelector('span');
    if (span) {
        span.textContent = '🔄 Reintentar Verificación';
    }
    
    // El botón ya tiene el event listener, solo cambiar apariencia
    button.classList.add('btn-retry');
    button.disabled = false;
}

// 🆕 MANEJAR FALLO CRÍTICO
function handleCriticalFailure() {
    console.log('💀 Critical failure - cleaning up and returning to start');
    
    // Limpiar timer
    if (userPhotoTimer) {
        userPhotoTimer.cleanup();
        userPhotoTimer = null;
    }
    
    // Parar cámara
    stopCamera();
    
    // Limpiar documento si es usuario nuevo
    if (!formData.documentExists) {
        cleanupDocumentOnTimeout();
    }
    
    // Mostrar mensaje y volver al inicio
    showError('El proceso de verificación ha fallado. Por favor, inicia nuevamente.');
    
    setTimeout(() => {
        hideError();
        resetToInitialState();
    }, 3000);
}

// ============================================
// SUCCESS SCREEN
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
// UTILITY FUNCTIONS
// ============================================

function resetToInitialState() {
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
    
    // Reset form
    document.getElementById('documentForm').reset();
    
    // Limpiar timers
    if (userPhotoTimer) {
        userPhotoTimer.cleanup();
        userPhotoTimer = null;
    }
    
    // Stop camera
    stopCamera();
    
    // Reset button text
    const button = document.getElementById('tomarFotoUsuario');
    if (button) {
        const span = button.querySelector('span');
        if (span) {
            span.textContent = '📸 Verificar Identidad';
        }
        button.classList.remove('btn-retry');
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
    
    return issues;
}

// ============================================
// EVENT LISTENERS
// ============================================

function setupEventListeners() {
    // Interface 1 - Form submission WITH DOCUMENT CHECK
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
        
        const submitButton = this.querySelector('button[type="submit"]');
        const submitButtonId = 'submitBtn';
        
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
                        permissionText.textContent = 'Documento encontrado en el sistema. Para completar la verificación biométrica, necesitamos acceso a su cámara web para validar su identidad.';
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
    
    // Permission interface - Allow camera
    document.getElementById('permitirCamara').addEventListener('click', async function() {
        showSpinner('permitirCamara');
        
        if (formData.documentExists) {
            const cameraStarted = await startCamera('videoUser');
            
            hideSpinner('permitirCamara');
            
            if (cameraStarted) {
                showInterface('interface3');
                startUserPhotoInterface();
            }
        } else {
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
    
    // 🆕 Interface 3 - Take user photo (MODIFICADO PARA REINTENTOS)
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
            showInterface('interfacePermission');
        } else {
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

    document.getElementById('numeroDocumento').addEventListener('input', function(e) {
        const onlyNumbers = e.target.value.replace(/[^[0-9]/g,'');
        
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

    document.getElementById('numeroDocumento').addEventListener('paste',function(e){
        setTimeout(() => {
            const onlyNumbers = e.target.value.replace(/[^0-9]/g,'');
            e.target.value = onlyNumbers;
        },10);
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
    
    console.log('✅ Rekognition POC Frontend initialized with retry logic');
}

// ============================================
// START APPLICATION
// ============================================

document.addEventListener('DOMContentLoaded', initializeApp);

window.addEventListener('beforeunload', function() {
    stopCamera();
    
    if (userPhotoTimer) {
        userPhotoTimer.cleanup();
    }
});