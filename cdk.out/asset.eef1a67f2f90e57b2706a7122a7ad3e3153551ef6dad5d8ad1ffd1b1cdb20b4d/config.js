// ============================================
// CONFIGURATION FILE
// ============================================

// This file will be dynamically updated during deployment with the actual API Gateway URL
// For local development, replace YOUR_API_GATEWAY_URL_HERE with your actual endpoint

window.API_GATEWAY_URL = 'YOUR_API_GATEWAY_URL_HERE';

// Example:
// window.API_GATEWAY_URL = 'https://abc123def456.execute-api.us-east-1.amazonaws.com/prod';

console.log('🔧 Config loaded - API Gateway URL:', window.API_GATEWAY_URL);