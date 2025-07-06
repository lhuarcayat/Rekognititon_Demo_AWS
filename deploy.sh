#!/bin/bash

# ============================================
# DEPLOYMENT SCRIPT - Rekognition POC
# ============================================

set -e  # Exit on any error

echo "🚀 Starting Rekognition POC Deployment..."
echo "============================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if required tools are installed
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed."
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        print_error "Node.js/npm is required but not installed."
        exit 1
    fi
    
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is required but not installed."
        exit 1
    fi
    
    if ! command -v cdk &> /dev/null; then
        print_error "AWS CDK is required but not installed. Run: npm install -g aws-cdk"
        exit 1
    fi
    
    print_success "All prerequisites are installed ✓"
}

# Setup Python virtual environment
setup_environment() {
    print_status "Setting up Python environment..."
    
    if [ ! -d ".venv" ]; then
        print_status "Creating Python virtual environment..."
        python3 -m venv .venv
    fi
    
    # Activate virtual environment
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        # Windows
        source .venv/Scripts/activate
    else
        # macOS/Linux
        source .venv/bin/activate
    fi
    
    print_status "Installing Python dependencies..."
    pip install -q -r requirements.txt boto3
    
    print_success "Python environment ready ✓"
}

# Bootstrap CDK if needed
bootstrap_cdk() {
    print_status "Checking CDK bootstrap status..."
    
    # Get AWS account and region
    AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
    AWS_REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")
    
    if [ -z "$AWS_ACCOUNT" ]; then
        print_error "Unable to get AWS account ID. Please check your AWS credentials."
        exit 1
    fi
    
    print_status "AWS Account: $AWS_ACCOUNT"
    print_status "AWS Region: $AWS_REGION"
    
    # Check if bootstrap stack exists
    BOOTSTRAP_STACK="CDKToolkit"
    if aws cloudformation describe-stacks --stack-name $BOOTSTRAP_STACK --region $AWS_REGION &>/dev/null; then
        print_success "CDK already bootstrapped ✓"
    else
        print_status "Bootstrapping CDK..."
        cdk bootstrap
        print_success "CDK bootstrap complete ✓"
    fi
}

# Deploy infrastructure
deploy_infrastructure() {
    print_status "Deploying infrastructure with CDK..."
    
    # Synthesize first to check for errors
    print_status "Synthesizing CDK stack..."
    cdk synth > /dev/null
    
    # Deploy
    print_status "Deploying to AWS (this may take 5-8 minutes)..."
    cdk deploy --require-approval never
    
    print_success "Infrastructure deployment complete ✓"
}

# Configure and deploy frontend
deploy_frontend() {
    print_status "Configuring and deploying frontend..."
    
    # Run the Python script to update frontend config and deploy
    python scripts/update_frontend_config.py RekognitionPocStack
    
    print_success "Frontend deployment complete ✓"
}

# Get and display deployment outputs
show_outputs() {
    print_status "Getting deployment outputs..."
    
    # Get stack outputs
    OUTPUTS=$(aws cloudformation describe-stacks --stack-name RekognitionPocStack --query 'Stacks[0].Outputs' 2>/dev/null || echo "[]")
    
    if [ "$OUTPUTS" != "[]" ]; then
        echo ""
        echo "============================================"
        echo "🎉 DEPLOYMENT SUCCESSFUL!"
        echo "============================================"
        
        # Extract specific outputs
        FRONTEND_URL=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="FrontendUrl") | .OutputValue' 2>/dev/null || echo "Not found")
        API_URL=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="ApiGatewayUrl") | .OutputValue' 2>/dev/null || echo "Not found")
        FRONTEND_BUCKET=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="FrontendBucketName") | .OutputValue' 2>/dev/null || echo "Not found")
        
        echo "🌐 Frontend URL: $FRONTEND_URL"
        echo "📡 API Gateway: $API_URL"
        echo "🪣 Frontend Bucket: $FRONTEND_BUCKET"
        echo "============================================"
        echo ""
        echo "✅ Your Rekognition POC is ready to use!"
        echo "📱 Open the Frontend URL in your browser to start testing"
        echo ""
    else
        print_warning "Could not retrieve stack outputs. Check AWS console for deployment details."
    fi
}

# Test basic functionality
test_deployment() {
    print_status "Running basic deployment tests..."
    
    # Test if API Gateway is responding
    API_URL=$(aws cloudformation describe-stacks --stack-name RekognitionPocStack --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' --output text 2>/dev/null || echo "")
    
    if [ -n "$API_URL" ]; then
        # Remove trailing slash
        API_URL=${API_URL%/}
        
        # Test presigned URLs endpoint
        print_status "Testing API endpoints..."
        
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/presigned-urls" \
            -H "Content-Type: application/json" \
            -d '{"fileName":"test.jpg","bucketType":"documents"}' 2>/dev/null || echo "000")
        
        if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "400" ]; then
            print_success "API Gateway is responding ✓"
        else
            print_warning "API Gateway test returned status: $HTTP_STATUS"
        fi
    else
        print_warning "Could not get API Gateway URL for testing"
    fi
    
    print_success "Basic tests completed ✓"
}

# Cleanup function
cleanup() {
    if [ $? -ne 0 ]; then
        print_error "Deployment failed!"
        echo ""
        echo "Troubleshooting steps:"
        echo "1. Check AWS credentials: aws sts get-caller-identity"
        echo "2. Check AWS region: aws configure get region"
        echo "3. Check CDK version: cdk --version"
        echo "4. Review CloudFormation events in AWS console"
        echo ""
        exit 1
    fi
}

# Set trap for cleanup
trap cleanup EXIT

# Main deployment process
main() {
    echo "Starting deployment process..."
    echo "Timestamp: $(date)"
    echo ""
    
    check_prerequisites
    setup_environment
    bootstrap_cdk
    deploy_infrastructure
    deploy_frontend
    show_outputs
    test_deployment
    
    print_success "🎉 Deployment completed successfully!"
    
    echo ""
    echo "Next steps:"
    echo "1. Open the Frontend URL in your browser"
    echo "2. Test the complete flow: Form → Document photo → User photo → Validation"
    echo "3. Check CloudWatch logs if you encounter any issues"
    echo ""
    echo "To destroy the stack later: cdk destroy"
    echo ""
}

# Run main function
main "$@"