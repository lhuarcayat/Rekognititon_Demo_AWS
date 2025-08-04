import aws_cdk as cdk
from infrastructure.rekognition_stack import RekognitionStack
import os

app = cdk.App()

account = os.environ.get('CDK_DEFAULT_ACCOUNT', app.account)
region = os.environ.get('CDK_DEFAULT_REGION', app.region)


RekognitionStack(
    app,
    'LivenessRekognitionPocStack',
    env=cdk.Environment(       
        account=account,
        region=region)
)

app.synth()