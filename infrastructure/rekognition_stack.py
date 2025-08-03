import aws_cdk as cdk
from aws_cdk import(
    Stack,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_s3_notifications as s3n,
    RemovalPolicy,
    Duration
)
from constructs import Construct
import os

class RekognitionStack(Stack):
    def __init__(self,scope:Construct, construct_id:str,**kwargs)->None:
        super().__init__(scope,construct_id,**kwargs)

        # Get validation mode from context or default to HYBRID
        validation_mode = self.node.try_get_context('validation_mode') or 'HYBRID'
        direct_compare_threshold = self.node.try_get_context('direct_compare_threshold') or '80.0'

# ======================================================================
#1. Bucket S3
# ======================================================================
        self.documents_bucket = s3.Bucket(
            self, 'DocumentsBucketBasic',
            bucket_name=f'rekognition-basic-documents-{self.account}-{self.region}',
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN
        )
        
        self.user_photos_bucket=s3.Bucket(
            self,'UserPhotosBucketBasic',
            bucket_name=f'rekognition-basic-user-photos-{self.account}-{self.region}',
            encryption=s3.BucketEncryption.S3_MANAGED,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id='user_photos_cleanup',
                    enabled=True,
                    expiration=Duration.days(120),
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER_INSTANT_RETRIEVAL,
                            transition_after=Duration.days(30)
                        )
                    ]
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.POST,s3.HttpMethods.PUT],
                    allowed_origins=['*'],
                    allowed_headers=['*'],
                    max_age=3000
                )
            ],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY
        )

    #============================================================
        # Tabla para metadatos de documentos indexados
        self.indexed_documents_table=dynamodb.Table(
            self,'IndexedDocumentsTableBasic',
            table_name='rekognition-basic-indexed-documents',
            partition_key=dynamodb.Attribute(
                name='document_id',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        self.indexed_documents_table.add_global_secondary_index(
            index_name='face-id-index',
            partition_key=dynamodb.Attribute(
                name='face_id',
                type=dynamodb.AttributeType.STRING
            )
        )
        
        self.indexed_documents_table.add_global_secondary_index(
            index_name='person-name-index',
            partition_key=dynamodb.Attribute(
                name='person_name',
                type=dynamodb.AttributeType.STRING
            )
        )

    #================================================
        # Tabla de resultados con campos adicionales para modo directo
        self.comparison_results_table=dynamodb.Table(
            self,'ComparisonResultsTableBasic',
            table_name='rekognition-basic-comparison-results',
            partition_key=dynamodb.Attribute(
                name='comparison_id',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='timestamp',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute='ttl',
            removal_policy=RemovalPolicy.DESTROY
        )

        self.comparison_results_table.add_global_secondary_index(
            index_name='user-image-index',
            partition_key=dynamodb.Attribute(
                name='user_image_key',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='timestamp',
                type=dynamodb.AttributeType.STRING
            )
        )
        
        self.comparison_results_table.add_global_secondary_index(
            index_name='validation-mode-index',
            partition_key=dynamodb.Attribute(
                name='validation_mode',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='confidence_score',
                type=dynamodb.AttributeType.NUMBER
            )
        )

    #======================== SHARED LAYER
        self.shared_layer = lambda_.LayerVersion(
            self, 'SharedLayer',
            layer_version_name='rekognition-basic-shared-layer',
            code=lambda_.Code.from_asset(
                'layers/shared',
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        'bash', '-c',
                        'pip install -r python/requirements.txt -t /asset-output/python && '
                        'cp -r python/shared /asset-output/python/'
                    ]
                )
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description='Shared utilities with auto-compiled dependencies'
        )

    #======================== IAM ROLES
        self.indexer_role=iam.Role(
            self,'IndexerLambdaRoleBasic',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
            ],
            inline_policies={
                'RekognitionIndexerBasicPolicy':iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'rekognition:IndexFaces',
                                'rekognition:CreateCollection',
                                'rekognition:DescribeCollection',
                                'rekognition:DetectFaces',
                                'rekognition:DeleteFaces'
                            ],
                            resources=['*']
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                's3:ListBucket'
                            ],
                            resources=[self.documents_bucket.bucket_arn]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                's3:GetObject'
                            ],
                            resources=[f'{self.documents_bucket.bucket_arn}/*']
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'dynamodb:PutItem',
                                'dynamodb:GetItem',
                                'dynamodb:UpdateItem',
                                'dynamodb:Scan'
                            ],
                            resources=[self.indexed_documents_table.table_arn]
                        )
                    ]
                )
            }
        )

        # Enhanced validator role with additional permissions for direct comparison
        self.validator_role = iam.Role(
            self,'ValidatorLambdaRoleBasic',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
            ],
            inline_policies={
                'RekognitionValidatorBasicPolicy':iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'rekognition:SearchFacesByImage',
                                'rekognition:CompareFaces',
                                'rekognition:DetectFaces'
                            ],
                            resources=['*']
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                's3:ListBucket'  
                            ],
                            resources=[
                                self.user_photos_bucket.bucket_arn,     
                                self.documents_bucket.bucket_arn         
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                's3:GetObject'
                            ],
                            resources=[
                                f'{self.user_photos_bucket.bucket_arn}/*',
                                f'{self.documents_bucket.bucket_arn}/*'
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'dynamodb:PutItem',
                                'dynamodb:GetItem',
                                'dynamodb:Query',
                                'dynamodb:Scan'
                            ],
                            resources=[
                                self.comparison_results_table.table_arn,
                                f"{self.comparison_results_table.table_arn}/index/*",
                                self.indexed_documents_table.table_arn,
                                f'{self.indexed_documents_table.table_arn}/index/*'
                            ]
                        )
                    ]
                )
            }
        )

    #==================================================== LAMBDA FUNCTIONS
        self.document_indexer = lambda_.Function(
            self, 'DocumentIndexerBasic',
            function_name='rekognition-basic-document-indexer',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/document_indexer'),
            role=self.indexer_role,
            timeout=Duration.minutes(5),
            memory_size=1024,
            layers=[
                self.shared_layer       
            ],
            environment={
                'COLLECTION_ID':'document-faces-basic-collection',
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET':self.documents_bucket.bucket_name
            }
        )

        # Enhanced user validator with dual mode support
        self.user_validator=lambda_.Function(
            self,'UserValidatorBasic',
            function_name='rekognition-basic-user-validator',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/user_validator'),
            role=self.validator_role,
            timeout=Duration.seconds(30),
            memory_size=512,
            layers=[
                self.shared_layer       
            ],
            environment={
                'COLLECTION_ID':'document-faces-basic-collection',
                'COMPARISON_RESULTS_TABLE':self.comparison_results_table.table_name,
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name,
                'USER_PHOTOS_BUCKET': self.user_photos_bucket.bucket_name,
                # NEW: Validation mode configuration
                'VALIDATION_MODE': validation_mode,
                'DIRECT_COMPARE_THRESHOLD': direct_compare_threshold
            }
        )

        # S3 event notifications (unchanged)
        self.user_photos_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.user_validator),
            s3.NotificationKeyFilter(suffix='.jpg')
        )
        self.user_photos_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED, 
            s3n.LambdaDestination(self.user_validator),
            s3.NotificationKeyFilter(suffix=".jpeg")
        )
        self.user_photos_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.user_validator), 
            s3.NotificationKeyFilter(suffix=".png")
        )

    #==================================================== OUTPUTS
        cdk.CfnOutput(
            self,'DocumentsBucketNameBasic',
            value=self.documents_bucket.bucket_name,
            description='Bucket for identity documents'
        )
        cdk.CfnOutput(
            self, 'UserPhotosBucketNameBasic',
            value=self.user_photos_bucket.bucket_name,
            description='Bucket for user photos'
        )
        cdk.CfnOutput(
            self,'IndexedDocumentsTableNameBasic',
            value=self.indexed_documents_table.table_name,
            description='DynamoDB table for indexed documents metadata'
        )
        cdk.CfnOutput(
            self,'ComparisonResultsTableNameBasic',
            value=self.comparison_results_table.table_name,
            description='DynamoDB table for comparison results'
        )
        cdk.CfnOutput(
            self,'ValidationMode',
            value=validation_mode,
            description='Current validation mode (HYBRID or DIRECT_COMPARE)'
        )
        cdk.CfnOutput(
            self,'DirectCompareThreshold',
            value=direct_compare_threshold,
            description='Threshold for direct comparison mode'
        )













                                        






















