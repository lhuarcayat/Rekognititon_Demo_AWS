import aws_cdk as cdk
from aws_cdk import(
    Stack,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_s3_notifications as s3n,
    aws_apigateway as apigateway,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    RemovalPolicy,
    Duration
)
from constructs import Construct
import os

class RekognitionStack(Stack):
    def __init__(self,scope:Construct, construct_id:str,**kwargs)->None:
        super().__init__(scope,construct_id,**kwargs)

# ======================================================================
# 1. S3 BUCKETS
# ======================================================================
        self.documents_bucket = s3.Bucket(
            self, 'LivenessDocumentsBucket',
            bucket_name=f'liveness-poc-documents-{self.account}-{self.region}',
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST, s3.HttpMethods.GET],
                    allowed_origins=['*'],
                    allowed_headers=['*'],
                    max_age=3000
                )
            ],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN
        )
        
        self.user_photos_bucket=s3.Bucket(
            self,'LivenessUserPhotosBucket',
            bucket_name=f'liveness-poc-user-photos-{self.account}-{self.region}',
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
                    allowed_methods=[s3.HttpMethods.POST,s3.HttpMethods.PUT, s3.HttpMethods.GET],
                    allowed_origins=['*'],
                    allowed_headers=['*'],
                    max_age=3000
                )
            ],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # FRONTEND BUCKET - Configured for CloudFront
        self.frontend_bucket = s3.Bucket(
            self, 'LivenessFrontendBucket',
            bucket_name = f'liveness-poc-frontend-{self.account}-{self.region}',
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY
        )

# ======================================================================
# 2. DYNAMODB TABLES
# ======================================================================
        # Table for indexed documents metadata
        self.indexed_documents_table=dynamodb.Table(
            self,'LivenessIndexedDocumentsTable',
            table_name='liveness-indexed-documents',
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
        
        # Table for comparison results
        self.comparison_results_table=dynamodb.Table(
            self,'LivenessComparisonResultsTable',
            table_name='liveness-comparison-results',
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

# ======================================================================
# 3. LAMBDA LAYERS
# ======================================================================
        self.shared_layer = lambda_.LayerVersion(
            self, 'LivenessSharedLayer',
            layer_version_name='liveness-poc-shared-layer',
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

# ======================================================================
# 4. IAM ROLES
# ======================================================================
        self.indexer_role=iam.Role(
            self,'LivenessIndexerLambdaRole',
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
                                's3:GetObject',
                                's3:DeleteObject'
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

        # UPDATED VALIDATOR ROLE - With permissions to invoke document indexer
        self.validator_role = iam.Role(
            self,'LivenessValidatorLambdaRole',
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
                                'rekognition:DetectFaces',
                                'rekognition:GetFaceLivenessSessionResults'
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
                                's3:GetObject',
                                's3:DeleteObject'
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
                        ),
                        # PERMISSION TO INVOKE DOCUMENT INDEXER
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'lambda:InvokeFunction'
                            ],
                            resources=[f'arn:aws:lambda:{self.region}:{self.account}:function:liveness-poc-document-indexer']
                        )
                    ]
                )
            }
        )

        # UPDATED API ROLE - With enhanced permissions
        self.api_role = iam.Role(
            self, 'LivenessApiLambdaRole',
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')                
            ],
            inline_policies={
                'ApiLambdaPolicy': iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                's3:PutObject',
                                's3:GetObject',
                                's3:HeadObject',
                                's3:DeleteObject'
                            ],
                            resources=[
                                f'{self.documents_bucket.bucket_arn}/*',
                                f'{self.user_photos_bucket.bucket_arn}/*'
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                's3:ListBucket'
                            ],
                            resources=[
                                self.documents_bucket.bucket_arn
                            ]
                        ),
                        iam.PolicyStatement(
                            effect =iam.Effect.ALLOW,
                            actions=[
                                'dynamodb:Query',
                                'dynamodb:Scan'
                            ],
                            resources=[
                                self.comparison_results_table.table_arn,
                                f'{self.comparison_results_table.table_arn}/index/*'
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'lambda:InvokeFunction'
                            ],
                            resources=[f'arn:aws:lambda:{self.region}:{self.account}:function:liveness-poc-document-indexer']
                        ),
                        # REKOGNITION PERMISSIONS FOR DOCUMENT INDEXER API
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'rekognition:DetectFaces',
                                'rekognition:CreateCollection',
                                'rekognition:DescribeCollection',
                                'rekognition:CreateFaceLivenessSession',
                                'rekognition:GetFaceLivenessSessionResults'
                            ],
                            resources=['*']
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'textract:AnalyzeDocument'
                            ],
                            resources=['*']
                        )
                    ]
                )
            }
        )

# ======================================================================
# 5. COGNITO IDENTITY POOL FOR FACE LIVENESS
# ======================================================================
        self.identity_pool = cognito.CfnIdentityPool(
            self, 'LivenessIdentityPool',
            identity_pool_name = 'liveness-poc-pool',
            allow_unauthenticated_identities = True,
            cognito_identity_providers = []
        )

        self.unauth_role = iam.Role(
            self, 'LivenessUnauthRole',
            assumed_by = iam.FederatedPrincipal(
                'cognito-identity.amazonaws.com',
                {
                    'StringEquals':{
                        'cognito-identity.amazonaws.com:aud': self.identity_pool.ref
                    },
                    'ForAnyValue:StringLike':{
                        'cognito-identity.amazonaws.com:amr':'unauthenticated'
                    }
                },
                'sts:AssumeRoleWithWebIdentity'
            ),
            inline_policies = {
                'LivenessPolicy': iam.PolicyDocument(
                    statements = [
                        iam.PolicyStatement(
                            effect = iam.Effect.ALLOW,
                            actions = [
                                'rekognition:StartFaceLivenessSession'
                            ],
                            resources = ['*']
                        )
                    ]
                )
            }
        )

        cognito.CfnIdentityPoolRoleAttachment(
            self, 'LivenessIdentityPoolRoleAttachment',
            identity_pool_id = self.identity_pool.ref,
            roles = {
                'unauthenticated': self.unauth_role.role_arn
            }
        )

# ======================================================================
# 6. LAMBDA FUNCTIONS
# ======================================================================
        self.document_indexer = lambda_.Function(
            self, 'LivenessDocumentIndexer',
            function_name='liveness-poc-document-indexer',
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
                'COLLECTION_ID':'liveness-document-faces-collection',
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET':self.documents_bucket.bucket_name
            }
        )
        
        # UPDATED USER VALIDATOR - With increased timeout and memory
        self.user_validator=lambda_.Function(
            self,'LivenessUserValidator',
            function_name='liveness-poc-user-validator',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/user_validator'),
            role=self.validator_role,
            timeout=Duration.minutes(2),  # INCREASED from 30s to 2 minutes
            memory_size=1024,  # INCREASED from 512 to 1024
            layers=[
                self.shared_layer
            ],
            environment={
                'COLLECTION_ID':'liveness-document-faces-collection',
                'COMPARISON_RESULTS_TABLE':self.comparison_results_table.table_name,
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name,
                'USER_PHOTOS_BUCKET': self.user_photos_bucket.bucket_name,
                'DOCUMENT_INDEXER_FUNCTION': 'liveness-poc-document-indexer'
            }
        )

# ======================================================================
# 7. API LAMBDA FUNCTIONS
# ======================================================================
        self.presigned_urls_lambda = lambda_.Function(
            self, 'LivenessPresignedUrlsLambda',
            function_name= 'liveness-poc-presigned-urls',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler ='handler.lambda_handler',
            code = lambda_.Code.from_asset('functions/presigned_urls'),
            role=self.api_role,
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                'DOCUMENTS_BUCKET':self.documents_bucket.bucket_name,
                'USER_PHOTOS_BUCKET':self.user_photos_bucket.bucket_name
            }
        )

        # UPDATED Document indexer API - With enhanced variables
        self.document_indexer_api = lambda_.Function(
            self, 'LivenessDocumentIndexerApi',
            function_name='liveness-poc-document-indexer-api',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/document_indexer_api'),
            role=self.api_role,
            timeout=Duration.seconds(30),
            memory_size=256,
            layers=[
                self.shared_layer
            ],
            environment={
                'DOCUMENT_INDEXER_FUNCTION': self.document_indexer.function_name,
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name,
                'COLLECTION_ID': 'liveness-document-faces-collection'
            }
        )

        # Check validation lambda
        self.check_validation_lambda = lambda_.Function(
            self, 'LivenessCheckValidationLambda',
            function_name='liveness-poc-check-validation',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/check_validation'),
            role=self.api_role,
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                'COMPARISON_RESULTS_TABLE': self.comparison_results_table.table_name
            }
        )

        # NEW LAMBDA: Check Document Exists
        self.check_document_exists_lambda = lambda_.Function(
            self, 'LivenessCheckDocumentExistsLambda',
            function_name='liveness-poc-check-document-exists',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/check_document_exists'),
            role=self.api_role,
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name
            }
        )

        # NEW LAMBDA: Cleanup Document
        self.cleanup_document_lambda = lambda_.Function(
            self, 'LivenessCleanupDocumentLambda',
            function_name='liveness-poc-cleanup-document',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/cleanup_document'),
            role=self.api_role,
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name
            }
        )
        
        # NEW LAMBDA: Face Liveness Session
        self.face_liveness_session = lambda_.Function(
            self, 'FaceLivenessSession',
            function_name = 'rekognition-poc-face-liveness-session',
            runtime = lambda_.Runtime.PYTHON_3_11,
            handler = 'handler.lambda_handler',
            code = lambda_.Code.from_asset('functions/face_liveness_session'),
            role = self.api_role,
            timeout = Duration.seconds(30),
            memory_size = 256,
            environment = {
                'USER_PHOTOS_BUCKET': self.user_photos_bucket.bucket_name
            }
        )

# ======================================================================
# 8. CLOUDFRONT DISTRIBUTION - SIMPLIFIED WITHOUT BUCKET DEPLOYMENT
# ======================================================================
        # Create Origin Access Identity for secure S3 access
        self.origin_access_identity = cloudfront.OriginAccessIdentity(
            self, 'LivenessFrontendOAI',
            comment='OAI for Liveness Rekognition POC Frontend'
        )
        
        # Allow CloudFront to access the bucket
        self.frontend_bucket.grant_read(self.origin_access_identity)

        # Create CloudFront distribution
        self.distribution = cloudfront.Distribution(
            self, 'LivenessFrontendDistribution',
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    self.frontend_bucket,
                    origin_access_identity=self.origin_access_identity
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                compress=True
            ),
            default_root_object='index.html',
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path='/index.html',
                    ttl=Duration.minutes(5)
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path='/index.html',
                    ttl=Duration.minutes(5)
                )
            ],
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            comment='Liveness Rekognition POC Frontend Distribution'
        )

# ======================================================================
# 9. API GATEWAY - With all endpoints
# ======================================================================
        self.api = apigateway.RestApi(
            self, 'LivenessRekognitionApi',
            rest_api_name='liveness-poc-api',
            description='API for Rekognition POC Frontend',
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=apigateway.Cors.DEFAULT_HEADERS
            )
        )

        # POST /presigned-urls
        presigned_resource = self.api.root.add_resource('presigned-urls')
        presigned_resource.add_method(
            'POST',
            apigateway.LambdaIntegration(self.presigned_urls_lambda)
        )

        # POST /index-document  
        index_resource = self.api.root.add_resource('index-document')
        index_resource.add_method(
            'POST',
            apigateway.LambdaIntegration(self.document_indexer_api)
        )

        # GET /check-validation/{numero_documento}
        check_resource = self.api.root.add_resource('check-validation')
        check_document_resource = check_resource.add_resource('{numero_documento}')
        check_document_resource.add_method(
            'GET',
            apigateway.LambdaIntegration(self.check_validation_lambda)
        )

        # POST /check-document
        check_doc_resource = self.api.root.add_resource('check-document')
        check_doc_resource.add_method(
            'POST',
            apigateway.LambdaIntegration(self.check_document_exists_lambda)
        )

        # POST /cleanup-document
        cleanup_doc_resource = self.api.root.add_resource('cleanup-document')
        cleanup_doc_resource.add_method(
            'POST',
            apigateway.LambdaIntegration(self.cleanup_document_lambda)
        )

        # Face Liveness endpoints
        liveness_session_resource = self.api.root.add_resource('liveness-session')
        liveness_session_resource.add_method(
            'POST',
            apigateway.LambdaIntegration(self.face_liveness_session)
        )

        session_id_resource = liveness_session_resource.add_resource('{sessionId}')
        session_id_resource.add_method(
            'GET',
            apigateway.LambdaIntegration(self.face_liveness_session)
        )

# ======================================================================
# 10. S3 TRIGGERS
# ======================================================================
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

# ======================================================================
# 11. OUTPUTS
# ======================================================================
        cdk.CfnOutput(
            self,'LivenessDocumentsBucketName',
            value=self.documents_bucket.bucket_name,
            description='Bucket for identity documents'
        )
        cdk.CfnOutput(
            self, 'LivenessUserPhotosBucketName',
            value=self.user_photos_bucket.bucket_name,
            description='Bucket for user photos'
        )

        cdk.CfnOutput(
            self, 'LivenessFrontendBucketName',
            value=self.frontend_bucket.bucket_name,
            description='Bucket for frontend hosting'
        )
        
        # HTTPS URL via CloudFront
        cdk.CfnOutput(
            self, 'LivenessFrontendUrl',
            value=f'https://{self.distribution.distribution_domain_name}',
            description='Frontend website URL (HTTPS via CloudFront)'
        )
        
        # CloudFront distribution ID
        cdk.CfnOutput(
            self, 'LivenessCloudFrontDistributionId',
            value=self.distribution.distribution_id,
            description='CloudFront distribution ID'
        )
        
        cdk.CfnOutput(
            self, 'LivenessApiGatewayUrl',
            value=self.api.url,
            description='API Gateway endpoint URL'
        )
        cdk.CfnOutput(
            self,'LivenessIndexedDocumentsTableName',
            value=self.indexed_documents_table.table_name,
            description='DynamoDB table for indexed documents metadata'
        )
        cdk.CfnOutput(
            self,'LivenessComparisonResultsTableName',
            value=self.comparison_results_table.table_name,
            description='DynamoDB table for comparison results'
        )
        cdk.CfnOutput(
            self, 'LivenessIdentityPoolId',
            value = self.identity_pool.ref,
            description = 'Cognito Identity Pool ID for Face Liveness'
        )