#!/usr/bin/env python3
"""
Script to update frontend configuration with actual API Gateway URL
This script should be run after CDK deployment to update the frontend config
"""

import json
import os
import sys
import subprocess
import boto3
from botocore.exceptions import ClientError

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
        
    except ClientError as e:
        raise Exception(f"Error accessing CloudFormation: {e}")

def update_config_file(api_gateway_url, config_path):
    """Update the frontend config.js file with the actual API Gateway URL"""
    
    config_content = f"""// ============================================
// CONFIGURATION FILE
// ============================================

// This file was automatically updated with the actual API Gateway URL
// Generated at deployment time

window.API_GATEWAY_URL = '{api_gateway_url}';

console.log('🔧 Config loaded - API Gateway URL:', window.API_GATEWAY_URL);"""

    try:
        # Write updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        print(f"✅ Updated {config_path} with API Gateway URL: {api_gateway_url}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating config file: {e}")
        return False

def deploy_frontend(bucket_name):
    """Deploy frontend to S3 bucket"""
    try:
        # Use AWS CLI to sync frontend files
        frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
        
        result = subprocess.run([
            'aws', 's3', 'sync', 
            frontend_path, 
            f's3://{bucket_name}/',
            '--delete'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Frontend deployed to S3 bucket: {bucket_name}")
            return True
        else:
            print(f"❌ Frontend deployment failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error deploying frontend: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python update_frontend_config.py <stack-name>")
        print("Example: python update_frontend_config.py RekognitionPocStack")
        sys.exit(1)
    
    stack_name = sys.argv[1]
    
    print(f"🚀 Updating frontend configuration for stack: {stack_name}")
    
    try:
        # Get stack outputs
        print("📋 Getting CloudFormation stack outputs...")
        outputs = get_stack_outputs(stack_name)
        
        # Extract required values
        api_gateway_url = outputs.get('ApiGatewayUrl')
        frontend_bucket = outputs.get('FrontendBucketName')
        
        if not api_gateway_url:
            raise Exception("ApiGatewayUrl not found in stack outputs")
        
        if not frontend_bucket:
            raise Exception("FrontendBucketName not found in stack outputs")
        
        # Remove trailing slash from API Gateway URL
        api_gateway_url = api_gateway_url.rstrip('/')
        
        print(f"📡 API Gateway URL: {api_gateway_url}")
        print(f"🪣 Frontend Bucket: {frontend_bucket}")
        
        # Update config file
        config_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist', 'config.js')
        
        if not update_config_file(api_gateway_url, config_path):
            sys.exit(1)
        
        # Deploy frontend
        print("🚀 Deploying frontend to S3...")
        if not deploy_frontend(frontend_bucket):
            sys.exit(1)
        
        # Print success message with URLs
        frontend_url = outputs.get('FrontendUrl', f'http://{frontend_bucket}.s3-website-us-east-1.amazonaws.com')
        
        print("\n" + "="*60)
        print("🎉 DEPLOYMENT SUCCESSFUL!")
        print("="*60)
        print(f"🌐 Frontend URL: {frontend_url}")
        print(f"📡 API Gateway: {api_gateway_url}")
        print(f"🪣 S3 Bucket: {frontend_bucket}")
        print("="*60)
        print("\n✅ Frontend is ready to use!")
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()