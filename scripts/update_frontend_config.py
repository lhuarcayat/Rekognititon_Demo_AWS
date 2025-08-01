#!/usr/bin/env python3
"""
Script rápido para deployment del frontend usando boto3 directamente
"""

import os
import sys
import boto3
import mimetypes
from pathlib import Path

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

def main():
    if len(sys.argv) != 2:
        print("Usage: python quick_deploy.py <stack-name>")
        print("Example: python quick_deploy.py RekognitionPocStack")
        sys.exit(1)
    
    stack_name = sys.argv[1]
    
    print("🚀 Quick Frontend Deployment")
    print("=" * 50)
    
    try:
        # Get stack outputs
        print("📋 Getting stack information...")
        outputs = get_stack_outputs(stack_name)
        
        bucket_name = outputs.get('FrontendBucketName')
        distribution_id = outputs.get('CloudFrontDistributionId')
        api_gateway_url = outputs.get('ApiGatewayUrl')
        frontend_url = outputs.get('FrontendUrl')
        
        if not bucket_name:
            raise Exception("FrontendBucketName not found in stack outputs")
        
        print(f"🪣 Frontend Bucket: {bucket_name}")
        print(f"🌐 Distribution ID: {distribution_id}")
        print(f"📡 API Gateway: {api_gateway_url}")
        
        # Sync frontend to S3
        if not sync_frontend_to_s3(bucket_name):
            raise Exception("Failed to sync frontend to S3")
        
        # Invalidate CloudFront cache
        if distribution_id:
            invalidate_cloudfront(distribution_id)
        
        # Print success
        print("\n" + "=" * 60)
        print("🎉 DEPLOYMENT SUCCESSFUL!")
        print("=" * 60)
        print(f"🌐 Frontend URL: {frontend_url}")
        print(f"📡 API Gateway: {api_gateway_url}")
        print(f"🪣 S3 Bucket: {bucket_name}")
        print("=" * 60)
        print("\n✅ Your application is ready!")
        
        if distribution_id:
            print("⏰ Note: Changes may take 5-15 minutes to appear due to CloudFront caching")
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()