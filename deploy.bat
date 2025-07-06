@echo off
REM ============================================
REM DEPLOYMENT SCRIPT - Rekognition POC (Windows)
REM ============================================

setlocal EnableDelayedExpansion

echo 🚀 Starting Rekognition POC Deployment...
echo ============================================

REM Check if required tools are installed
echo [INFO] Checking prerequisites...

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is required but not installed.
    exit /b 1
)

where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js/npm is required but not installed.
    exit /b 1
)

where aws >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] AWS CLI is required but not installed.
    exit /b 1
)

where cdk >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] AWS CDK is required but not installed. Run: npm install -g aws-cdk
    exit /b 1
)

echo [SUCCESS] All prerequisites are installed ✓

REM Setup Python virtual environment
echo [INFO] Setting up Python environment...

if not exist ".venv" (
    echo [INFO] Creating Python virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

echo [INFO] Installing Python dependencies...
pip install -q -r requirements.txt boto3

echo [SUCCESS] Python environment ready ✓

REM Get AWS info
echo [INFO] Checking AWS configuration...
for /f "tokens=*" %%i in ('aws sts get-caller-identity --query Account --output text 2^>nul') do set AWS_ACCOUNT=%%i
for /f "tokens=*" %%i in ('aws configure get region 2^>nul') do set AWS_REGION=%%i

if "%AWS_REGION%"=="" set AWS_REGION=us-east-1

if "%AWS_ACCOUNT%"=="" (
    echo [ERROR] Unable to get AWS account ID. Please check your AWS credentials.
    exit /b 1
)

echo [INFO] AWS Account: %AWS_ACCOUNT%
echo [INFO] AWS Region: %AWS_REGION%

REM Check CDK bootstrap
echo [INFO] Checking CDK bootstrap status...
aws cloudformation describe-stacks --stack-name CDKToolkit --region %AWS_REGION% >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Bootstrapping CDK...
    cdk bootstrap
    echo [SUCCESS] CDK bootstrap complete ✓
) else (
    echo [SUCCESS] CDK already bootstrapped ✓
)

REM Deploy infrastructure
echo [INFO] Deploying infrastructure with CDK...

echo [INFO] Synthesizing CDK stack...
cdk synth >nul

echo [INFO] Deploying to AWS (this may take 5-8 minutes)...
cdk deploy --require-approval never

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Infrastructure deployment failed!
    exit /b 1
)

echo [SUCCESS] Infrastructure deployment complete ✓

REM Configure and deploy frontend
echo [INFO] Configuring and deploying frontend...
python scripts\update_frontend_config.py RekognitionPocStack

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Frontend deployment failed!
    exit /b 1
)

echo [SUCCESS] Frontend deployment complete ✓

REM Get deployment outputs
echo [INFO] Getting deployment outputs...

echo.
echo ============================================
echo 🎉 DEPLOYMENT SUCCESSFUL!
echo ============================================

REM Get stack outputs (simplified for Windows)
aws cloudformation describe-stacks --stack-name RekognitionPocStack --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" --output text > temp_frontend_url.txt 2>nul
aws cloudformation describe-stacks --stack-name RekognitionPocStack --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" --output text > temp_api_url.txt 2>nul
aws cloudformation describe-stacks --stack-name RekognitionPocStack --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text > temp_bucket.txt 2>nul

if exist temp_frontend_url.txt (
    set /p FRONTEND_URL=<temp_frontend_url.txt
    echo 🌐 Frontend URL: !FRONTEND_URL!
    del temp_frontend_url.txt
)

if exist temp_api_url.txt (
    set /p API_URL=<temp_api_url.txt
    echo 📡 API Gateway: !API_URL!
    del temp_api_url.txt
)

if exist temp_bucket.txt (
    set /p FRONTEND_BUCKET=<temp_bucket.txt
    echo 🪣 Frontend Bucket: !FRONTEND_BUCKET!
    del temp_bucket.txt
)

echo ============================================
echo.
echo ✅ Your Rekognition POC is ready to use!
echo 📱 Open the Frontend URL in your browser to start testing
echo.
echo Next steps:
echo 1. Open the Frontend URL in your browser
echo 2. Test the complete flow: Form → Document photo → User photo → Validation
echo 3. Check CloudWatch logs if you encounter any issues
echo.
echo To destroy the stack later: cdk destroy
echo.

pause
exit /b 0