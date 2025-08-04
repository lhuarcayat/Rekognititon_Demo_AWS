// ============================================
// CORRECTED CONFIGURATION FOR AWS AMPLIFY V6
// ============================================

// This file is automatically updated with the actual API Gateway URL
// Generated at deployment time

window.API_GATEWAY_URL = 'https://ft6723fro2.execute-api.us-east-1.amazonaws.com/prod/';

// ✅ CRITICAL: Identity Pool ID for AWS Face Liveness
// This should be automatically replaced by the deployment script
// with the actual Identity Pool ID from CloudFormation output
window.LIVENESS_IDENTITY_POOL_ID = 'us-east-1:40d7a164-7725-44da-9bde-eff19dbec4d2';

// AWS Region configuration
window.AWS_REGION = 'us-east-1';

console.log('🔧 Config loaded - API Gateway URL:', window.API_GATEWAY_URL);
console.log('🔧 Config loaded - Identity Pool ID:', window.LIVENESS_IDENTITY_POOL_ID);
console.log('🔧 Config loaded - AWS Region:', window.AWS_REGION);

// ✅ CORRECTED: Amplify v6 configuration object
window.AMPLIFY_CONFIG = {
    Auth: {
        Cognito: {
            identityPoolId: window.LIVENESS_IDENTITY_POOL_ID,
            region: window.AWS_REGION,
            allowGuestAccess: true
        }
    }
};

// Validation checks
if (window.LIVENESS_IDENTITY_POOL_ID && 
    window.LIVENESS_IDENTITY_POOL_ID !== 'us-east-1:YOUR_IDENTITY_POOL_ID_FROM_CDK' &&
    window.LIVENESS_IDENTITY_POOL_ID !== 'us-east-1:REPLACE_WITH_YOUR_ACTUAL_IDENTITY_POOL_ID') {
    console.log('✅ Amplify Config ready for Face Liveness');
    console.log('✅ Identity Pool configured:', window.LIVENESS_IDENTITY_POOL_ID);
} else {
    console.warn('⚠️  Identity Pool ID not configured correctly - Face Liveness may not work');
    console.warn('⚠️  Current value:', window.LIVENESS_IDENTITY_POOL_ID);
    console.warn('⚠️  Expected format: us-east-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx');
    console.warn('⚠️  Run deployment script to get the correct Identity Pool ID from CloudFormation');
}

// API Gateway validation
if (window.API_GATEWAY_URL && window.API_GATEWAY_URL !== 'YOUR_API_GATEWAY_URL_HERE') {
    console.log('✅ API Gateway URL configured');
} else {
    console.warn('⚠️  API Gateway URL not configured');
}

// Environment info
console.log('🌍 Environment Info:');
console.log('   - API Gateway:', window.API_GATEWAY_URL);
console.log('   - Identity Pool:', window.LIVENESS_IDENTITY_POOL_ID);
console.log('   - Region:', window.AWS_REGION);
console.log('   - Amplify Config Ready:', typeof window.AMPLIFY_CONFIG !== 'undefined');