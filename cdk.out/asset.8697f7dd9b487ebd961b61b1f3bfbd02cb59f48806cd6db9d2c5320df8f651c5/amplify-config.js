window.AMPLIFY_CONFIG = {
    Auth: {
        Cognito: {
            region: 'us-east-1',
            identityPoolId: 'YOUR_IDENTITY_POOL_ID_FROM_CDK_OUTPUT',
            allowGuestAccess: true
        }
    }
};