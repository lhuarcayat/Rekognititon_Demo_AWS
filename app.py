import aws_cdk as cdk
from infrastructure.rekognition_stack import RekognitionStack

app = cdk.App()

RekognitionStack(
    app,
    'RekognitionPocBasicStack',
    env=cdk.Environment(
        account=app.node.try_get_context('account'),
        region=app.node.try_get_context('region') or 'us-east-1'
    )
)

app.synth()