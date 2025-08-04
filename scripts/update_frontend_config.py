#!/usr/bin/env python3
"""
Script corregido para deployment del frontend con AWS Face Liveness v6
"""

import os
import sys
import boto3
import mimetypes
from pathlib import Path
import re

def update_config_with_identity_pool(config_file_path, api_gateway_url, identity_pool_id):
    """Update config.js with actual Identity Pool ID and API Gateway URL"""
    try:
        print(f"📝 Updating config file: {config_file_path}")
        
        # Read current config
        with open(config_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update API Gateway URL
        content = re.sub(
            r"window\.API_GATEWAY_URL = '[^']*';",
            f"window.API_GATEWAY_URL = '{api_gateway_url}';",
            content
        )
        
        # Update Identity Pool ID - multiple patterns to catch different formats
        patterns = [
            r"window\.LIVENESS_IDENTITY_POOL_ID = '[^']*';",
            r"window\.LIVENESS_IDENTITY_POOL_ID = 'us-east-1:YOUR_IDENTITY_POOL_ID_FROM_CDK';",
            r"window\.LIVENESS_IDENTITY_POOL_ID = 'us-east-1:REPLACE_WITH_YOUR_ACTUAL_IDENTITY_POOL_ID';"
        ]
        
        for pattern in patterns:
            content = re.sub(
                pattern,
                f"window.LIVENESS_IDENTITY_POOL_ID = '{identity_pool_id}';",
                content
            )
        
        # Write updated config
        with open(config_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Config updated successfully")
        print(f"   API Gateway: {api_gateway_url}")
        print(f"   Identity Pool: {identity_pool_id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating config: {str(e)}")
        return False

def upload_file_to_s3(s3_client, file_path, bucket_name, s3_key):
    """Upload a single file to S3 with correct content type"""
    try:
        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Special handling for common web files
        if file_path.endswith('.js'):
            content_type = 'application/javascript'
        elif file_path.endswith('.css'):
            content_type = 'text/css'
        elif file_path.endswith('.html'):
            content_type = 'text/html'
        
        extra_args = {
            'ContentType': content_type
        }
        
        # Add cache control for static assets
        if file_path.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.ico')):
            extra_args['CacheControl'] = 'public, max-age=31536000'  # 1 year
        else:
            extra_args['CacheControl'] = 'public, max-age=300'  # 5 minutes
        
        s3_client.upload_file(file_path, bucket_name, s3_key, ExtraArgs=extra_args)
        return True
        
    except Exception as e:
        print(f"❌ Error uploading {s3_key}: {str(e)}")
        return False

def sync_frontend_to_s3(bucket_name):
    """Sync frontend files to S3 using boto3"""
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3')
        
        # Get frontend directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        frontend_dir = os.path.join(script_dir, '..', 'frontend', 'dist')
        frontend_path = Path(frontend_dir)
        
        if not frontend_path.exists():
            print(f"❌ Frontend directory not found: {frontend_path}")
            return False
        
        print(f"📁 Frontend directory: {frontend_path}")
        print(f"🪣 Target bucket: {bucket_name}")
        
        # Get all files in frontend directory
        files_to_upload = []
        for file_path in frontend_path.rglob('*'):
            if file_path.is_file():
                # Calculate relative path for S3 key
                relative_path = file_path.relative_to(frontend_path)
                s3_key = str(relative_path).replace('\\', '/')  # Fix Windows path separators
                files_to_upload.append((str(file_path), s3_key))
        
        if not files_to_upload:
            print("❌ No files found to upload")
            return False
        
        print(f"📦 Found {len(files_to_upload)} files to upload")
        
        # Upload files one by one
        successful_uploads = 0
        for file_path, s3_key in files_to_upload:
            print(f"⬆️  Uploading: {s3_key}")
            if upload_file_to_s3(s3_client, file_path, bucket_name, s3_key):
                successful_uploads += 1
            else:
                print(f"❌ Failed to upload: {s3_key}")
        
        print(f"\n✅ Successfully uploaded {successful_uploads}/{len(files_to_upload)} files")
        
        if successful_uploads == len(files_to_upload):
            print("🎉 All files uploaded successfully!")
            return True
        else:
            print("⚠️  Some files failed to upload")
            return False
        
    except Exception as e:
        print(f"❌ Error syncing to S3: {str(e)}")
        return False

def invalidate_cloudfront(distribution_id):
    """Invalidate CloudFront cache"""
    try:
        cloudfront_client = boto3.client('cloudfront')
        
        print(f"🔄 Creating CloudFront invalidation for distribution: {distribution_id}")
        
        response = cloudfront_client.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                'Paths': {
                    'Quantity': 1,
                    'Items': ['/*']
                },
                'CallerReference': str(hash(f"{distribution_id}-{os.urandom(8).hex()}"))
            }
        )
        
        invalidation_id = response['Invalidation']['Id']
        print(f"✅ CloudFront invalidation created: {invalidation_id}")
        print("⏰ Cache invalidation will take 5-15 minutes to complete")
        
        return True
        
    except Exception as e:
        print(f"❌ Error invalidating CloudFront: {str(e)}")
        return False

def get_stack_outputs(stack_name):
    """Get CloudFormation stack outputs"""
    try:
        cloudformation = boto3.client('cloudformation')
        response = cloudformation.describe_stacks(StackName=stack_name)
        
        if not response['Stacks']:
            raise Exception(f"Stack {stack_name} not found")
        
        outputs = {}
        stack_outputs = response['Stacks'][0].get('Outputs', [])
        
        for output in stack_outputs:
            outputs[output['OutputKey']] = output['OutputValue']
        
        return outputs
        
    except Exception as e:
        raise Exception(f"Error accessing CloudFormation: {e}")

def verify_amplify_configuration():
    """Verify that the Amplify configuration is correct"""
    print("🔍 Verifying Amplify v6 configuration...")
    
    # Check if config.js exists and has the right structure
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file_path = os.path.join(script_dir, '..', 'frontend', 'dist', 'config.js')
    
    if not os.path.exists(config_file_path):
        print("❌ config.js not found")
        return False
    
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for Amplify v6 configuration patterns
        required_patterns = [
            'window.AMPLIFY_CONFIG',
            'Auth:',
            'Cognito:',
            'identityPoolId:',
            'allowGuestAccess: true'
        ]
        
        missing_patterns = []
        for pattern in required_patterns:
            if pattern not in content:
                missing_patterns.append(pattern)
        
        if missing_patterns:
            print(f"❌ Missing Amplify v6 configuration patterns: {missing_patterns}")
            return False
        
        print("✅ Amplify v6 configuration structure verified")
        return True
        
    except Exception as e:
        print(f"❌ Error verifying configuration: {str(e)}")
        return False

def check_iam_permissions():
    """Check if the current AWS credentials have necessary permissions"""
    try:
        print("🔐 Checking AWS credentials and permissions...")
        
        # Check basic AWS access
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        
        print(f"✅ AWS Identity: {identity.get('Arn', 'Unknown')}")
        
        # Check CloudFormation access (without MaxResults parameter)
        cloudformation = boto3.client('cloudformation')
        cloudformation.list_stacks()
        print("✅ CloudFormation access confirmed")
        
        # Check S3 access
        s3 = boto3.client('s3')
        s3.list_buckets()
        print("✅ S3 access confirmed")
        
        # Check Cognito access
        cognito = boto3.client('cognito-identity')
        # Just check if we can make a basic call without errors
        try:
            cognito.list_identity_pools(MaxResults=1)
            print("✅ Cognito Identity access confirmed")
        except Exception as cognito_error:
            print(f"⚠️  Cognito access check failed: {str(cognito_error)}")
            print("💡 This might not affect deployment if Identity Pool already exists")
        
        return True
        
    except Exception as e:
        print(f"❌ AWS permissions check failed: {str(e)}")
        print("💡 Ensure your AWS credentials have the necessary permissions")
        return False

def validate_identity_pool_permissions(identity_pool_id):
    """Validate that the Identity Pool has correct permissions for Face Liveness"""
    try:
        print(f"🔍 Validating Identity Pool permissions: {identity_pool_id}")
        
        cognito_identity = boto3.client('cognito-identity')
        
        # Get identity pool details
        pool_details = cognito_identity.describe_identity_pool(
            IdentityPoolId=identity_pool_id
        )
        
        print(f"✅ Identity Pool found: {pool_details.get('IdentityPoolName', 'Unknown')}")
        print(f"   - Allow unauthenticated: {pool_details.get('AllowUnauthenticatedIdentities', False)}")
        
        # Get identity pool roles
        try:
            roles = cognito_identity.get_identity_pool_roles(
                IdentityPoolId=identity_pool_id
            )
            
            unauth_role = roles.get('Roles', {}).get('unauthenticated')
            if unauth_role:
                print(f"✅ Unauthenticated role found: {unauth_role}")
            else:
                print("⚠️  No unauthenticated role configured")
                
        except Exception as role_error:
            print(f"⚠️  Could not check roles: {str(role_error)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Identity Pool validation failed: {str(e)}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python update_frontend_config.py <stack-name>")
        print("Example: python update_frontend_config.py LivenessRekognitionPocStack")
        sys.exit(1)
    
    stack_name = sys.argv[1]
    
    print("🚀 AWS Face Liveness v6 Frontend Deployment")
    print("=" * 60)
    
    try:
        # Check AWS permissions first (but don't fail if minor issues)
        print("🔐 Performing initial AWS permissions check...")
        permissions_ok = check_iam_permissions()
        
        if not permissions_ok:
            print("⚠️  Some permission checks failed, but continuing...")
            print("💡 If deployment fails, check AWS credentials and permissions")
        
        # Verify Amplify configuration structure
        if not verify_amplify_configuration():
            print("⚠️  Configuration verification failed, but continuing...")
        
        # Get stack outputs
        print("📋 Getting stack information...")
        outputs = get_stack_outputs(stack_name)
        
        bucket_name = outputs.get('LivenessFrontendBucketName')
        distribution_id = outputs.get('LivenessCloudFrontDistributionId')
        api_gateway_url = outputs.get('LivenessApiGatewayUrl')
        frontend_url = outputs.get('LivenessFrontendUrl')
        identity_pool_id = outputs.get('LivenessIdentityPoolId')
        
        # Validation
        if not bucket_name:
            raise Exception("LivenessFrontendBucketName not found in stack outputs")
        
        if not identity_pool_id:
            raise Exception("LivenessIdentityPoolId not found in stack outputs - required for Face Liveness")
        
        if not api_gateway_url:
            raise Exception("LivenessApiGatewayUrl not found in stack outputs")
        
        print(f"🪣 Frontend Bucket: {bucket_name}")
        print(f"🌐 Distribution ID: {distribution_id}")
        print(f"📡 API Gateway: {api_gateway_url}")
        print(f"🔐 Identity Pool ID: {identity_pool_id}")
        
        # Validate Identity Pool ID format
        identity_pool_pattern = r'^us-east-1:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(identity_pool_pattern, identity_pool_id):
            print(f"⚠️  Warning: Identity Pool ID format might be incorrect: {identity_pool_id}")
            print(f"⚠️  Expected format: us-east-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        else:
            print("✅ Identity Pool ID format is correct")
        
        # Validate Identity Pool permissions
        validate_identity_pool_permissions(identity_pool_id)
        
        # Update config.js with real values
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file_path = os.path.join(script_dir, '..', 'frontend', 'dist', 'config.js')
        
        if not update_config_with_identity_pool(config_file_path, api_gateway_url, identity_pool_id):
            raise Exception("Failed to update config file")
        
        # Sync frontend to S3
        if not sync_frontend_to_s3(bucket_name):
            raise Exception("Failed to sync frontend to S3")
        
        # Invalidate CloudFront cache
        if distribution_id:
            invalidate_cloudfront(distribution_id)
        
        # Print success
        print("\n" + "=" * 70)
        print("🎉 AWS FACE LIVENESS V6 DEPLOYMENT SUCCESSFUL!")
        print("=" * 70)
        print(f"🌐 Frontend URL: {frontend_url}")
        print(f"📡 API Gateway: {api_gateway_url}")
        print(f"🔐 Identity Pool: {identity_pool_id}")
        print(f"🪣 S3 Bucket: {bucket_name}")
        print("=" * 70)
        print("\n✅ Your application now uses REAL AWS Face Liveness v6!")
        print("📝 This uses the official AWS Amplify v6 with React 18")
        
        if distribution_id:
            print("⏰ Note: Changes may take 5-15 minutes to appear due to CloudFront caching")
        
        print("\n🔧 Next steps:")
        print("1. Open your browser and navigate to the Frontend URL")
        print("2. Open browser console (F12) to check for any errors")
        print("3. Test the Face Liveness functionality")
        print("4. Verify that all library checks show ✅ in the console")
        
        print(f"\n🔍 Debugging commands:")
        print(f"# Check stack outputs:")
        print(f"aws cloudformation describe-stacks --stack-name {stack_name} --query \"Stacks[0].Outputs\"")
        print(f"\n# Check Identity Pool:")
        print(f"aws cognito-identity describe-identity-pool --identity-pool-id {identity_pool_id}")
        print(f"\n# Check Identity Pool roles:")
        print(f"aws cognito-identity get-identity-pool-roles --identity-pool-id {identity_pool_id}")
        
        print(f"\n📚 Documentation:")
        print("- AWS Amplify v6: https://docs.amplify.aws/")
        print("- Face Liveness: https://docs.amplify.aws/react/connected-components/liveness/")
        print("- Rekognition: https://docs.aws.amazon.com/rekognition/latest/dg/face-liveness.html")
        
        print(f"\n🐛 Troubleshooting:")
        print("- If Face Liveness doesn't load: Check Identity Pool permissions")
        print("- If 'Access Denied' errors: Verify IAM roles have Rekognition permissions")
        print("- If library errors: Check browser console for missing dependencies")
        print("- If CORS errors: Verify API Gateway CORS configuration")
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Ensure your CDK stack deployed successfully:")
        print(f"   cdk deploy {stack_name}")
        print("2. Check that all required outputs exist in CloudFormation")
        print("3. Verify AWS credentials are configured correctly:")
        print("   aws sts get-caller-identity")
        print("4. Check that the Identity Pool exists:")
        print(f"   aws cognito-identity describe-identity-pool --identity-pool-id <pool-id>")
        print("5. Verify S3 bucket permissions for upload")
        sys.exit(1)

if __name__ == "__main__":
    main()