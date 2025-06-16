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
# ======================================================================
#1. Bucket S3
# ======================================================================
        self.documents_bucket = s3.Bucket(
            self, 'DocumentsBucket',
            bucket_name=f'rekognition-poc-documents-{self.account}-{self.region}',
            versioning=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            # lifecycle_rules=[
            #     s3.LifecycleRule(
            #         id='documents_archive',
            #         transitions=[
            #             s3.Transition(
            #                 storage_class=s3.StorageClass.GLACIER,
            #                 transition_after=Duration.days(30)
            #             ),
            #             s3.Transition(
            #                 storage_class=s3.StorageClass.DEEP_ARCHIVE,
            #                 transition_after=Duration.days(90)
            #             )
            #         ]
            #     )
            # ],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN
        )
        self.user_photos_bucket=s3.Bucket(
            self,'UserPhotosBucket',
            bucket_name=f'rekognition-poc-user-photos-{self.account}--{self.region}',
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
            removal_policy=RemovalPolicy.DESTROY
        )
    #============================================================
        #Tabla para metadatos de documentos indexados
        self.indexed_documents_table=dynamodb.Table(
            self,'IndexedDocumentsTable',
            table_name='rekognition-indexed-documents',
            partition_key=dynamodb.Attribute(
                name='document_id',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            global_secondary_indexes=[
                dynamodb.GlobalSecondaryIndex(
                    index_name='face-id-index',
                    partition_key=dynamodb.Attribute(
                        name='face_id',
                        type=dynamodb.AttributeType.STRING
                    )
                ),
                dynamodb.GlobalSecondaryIndex(
                    index_name='person-name-index',
                    partition_key=dynamodb.Attribute(
                        name='person-name',
                        type=dynamodb.AttributeType.STRING
                    )
                )
            ],
            removal_policy=RemovalPolicy.DESTROY
        )

    #================================================
        self.comparison_results_table=dynamodb.Table(
            self,'ComparisonResultsTable',
            table_name='rekognition-comparison-results',
            partition_key=dynamodb.Attribute(
                name='comparison_id',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='timestamp',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            global_secondary_indexes=[
                dynamodb.GlobalSecondaryIndex(
                    index_name='user-image-index',
                    partition_key=dynamodb.Attribute(
                        name='user_image_key',
                        type=dynamodb.AttributeType.STRING
                    ),
                    sort_key=dynamodb.Attribute(
                        name='timestamp',
                        type=dynamodb.AttributeType.STRING
                    )
                ),
                dynamodb.GlobalSecondaryIndex(
                    index_name='face-id-index',
                    partition_key=dynamodb.Attribute(
                        name='matched_face_id',
                        type=dynamodb.AttributeType.STRING
                    ),
                    sort_key=dynamodb.Attribute(
                        name='confidence_score',
                        type=dynamodb.AttributeType.NUMBER
                    )
                )
            ],
            time_to_live_attribute='ttl',
            removal_policy=RemovalPolicy.DESTROY
        )
    #========================IAM ROLE
        self.indexer_role=iam.Role(
            self,'IndexerLambdaRole',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
            ],
            inline_policies={
                'RekognitionIndexerPolicy':iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'rekognition:IndexFaces',
                                'rekognition:CreateCollection',
                                'rekognition:DescribeCollection',
                                'rekognition:DetectFaces'
                            ],
                            resources=['*']
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
                                'dynamodb:UpdateItem'
                            ],
                            resources=[self.indexed_documents_table.table_arn]
                        )
                    ]
                )
            }
        )

        self.validator_role = iam.Role(
            self,'ValidatorLambdaRole',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
            ],
            inline_policies={
                'RekognitionValidatorPolicy':iam.PolicyDocument(
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
                                'dynamodb:Query'
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
    #====================================================
        self.document_indexer = lambda_.Function(
            self, 'DocumentIndexer',
            function_name='rekognition-poc-document-indexer',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('lambda_code/document_indexer'),
            role=self.indexer_role,
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                'COLLECTION_ID':'document-faces-collection',
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET':self.documents_bucket.bucket_name
            }
        )
        self.user_validator=lambda_.Function(
            self,'UserValidator',
            function_name='rekognition-poc-user-validator',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('lambda_code/user_validator'),
            role=self.validator_role,
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                'COLLECTION_ID':'document-faces-collection',
                'COMPARISON_RESULTS_TABLE':self.comparison_results_table.table_name,
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name  
            }
        )
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
        cdk.CfnOutput(
            self,'DocumentsBucketName',
            value=self.documents_bucket.bucket_name,
            description='Bucket for identity documents'
        )
        cdk.CfnOutput(
            self, 'UserPhotosBucketName',
            value=self.user_photos_bucket.bucket_name,
            description='Bucket for user photos'
        )
        cdk.CfnOutput(
            self,'IndexedDocumentsTableName',
            value=self.indexed_documents_table.table_name,
            description='DynamoDB table for indexed documents metadata'
        )
        cdk.CfnOutput(
            self,'ComparisonResultsTableName',
            value=self.comparison_results_table.table_name,
            description='DynamoDB table for comparison results'
        )













                                        






















