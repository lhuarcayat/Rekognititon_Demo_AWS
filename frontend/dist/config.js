// ============================================
// CORRECTED CONFIGURATION FOR AWS AMPLIFY V5
// ============================================

// This file is automatically updated with the actual API Gateway URL
// Generated at deployment time

window.API_GATEWAY_URL = 'https://ft6723fro2.execute-api.us-east-1.amazonaws.com/prod/';

// ✅ CRITICAL: Identity Pool ID for AWS Face Liveness
// Replace this with your actual Identity Pool ID from CloudFormation output
window.LIVENESS_IDENTITY_POOL_ID = 'us-east-1:40d7a164-7725-44da-9bde-eff19dbec4d2';

// AWS Region configuration
window.AWS_REGION = 'us-east-1';

console.log('🔧 Config loaded - API Gateway URL:', window.API_GATEWAY_URL);
console.log('🔧 Config loaded - Identity Pool ID:', window.LIVENESS_IDENTITY_POOL_ID);

// ✅ CORRECTED: Amplify v5 configuration object
window.AMPLIFY_CONFIG = {
    Auth: {
        identityPoolId: window.LIVENESS_IDENTITY_POOL_ID,
        region: window.AWS_REGION
    }
};

if (window.LIVENESS_IDENTITY_POOL_ID && 
    window.LIVENESS_IDENTITY_POOL_ID !== 'us-east-1:YOUR_IDENTITY_POOL_ID_FROM_CDK' &&
    window.LIVENESS_IDENTITY_POOL_ID !== 'us-east-1:REPLACE_WITH_YOUR_ACTUAL_IDENTITY_POOL_ID') {
    console.log('✅ Amplify Config ready for Face Liveness');
} else {
    console.warn('⚠️  Identity Pool ID not configured - Face Liveness may not work');
    console.warn('⚠️  Run: aws cloudformation describe-stacks --stack-name LivenessRekognitionPocStack --query "Stacks[0].Outputs[?OutputKey==\`LivenessIdentityPoolId\`].OutputValue" --output text');
}