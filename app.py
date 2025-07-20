import aws_cdk as cdk
from infrastructure.rekognition_stack import RekognitionStack

app = cdk.App()

RekognitionStack(
    app,
    'RekognitionPocStack',
)

app.synth()