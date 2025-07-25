export const awsConfig = {
  Auth: {
    Cognito: {
      identityPoolId: 'us-east-1:5faa0404-5baa-4f4e-904a-09d3c998f2c2',
      region: 'us-east-1'
    }
  },
  Storage: {
    S3: {
      bucket: 'liveness-audit-bucket',
      region: 'us-east-1'
    }
  }
};