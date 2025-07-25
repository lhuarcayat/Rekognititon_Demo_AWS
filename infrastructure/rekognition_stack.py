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
    aws_apigateway as apigateway,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
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
            bucket_name=f'rekog-poc-documents-{self.account}',
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
            self,'UserPhotosBucket',
            bucket_name=f'rekog-poc-user-photos-{self.account}',
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
        
        # 🆕 FRONTEND BUCKET - Configurado para CloudFront (NO website hosting)
        self.frontend_bucket = s3.Bucket(
            self, 'FrontendBucket',
            bucket_name = f'rekognition-poc-frontend-{self.account}-{self.region}',
            encryption=s3.BucketEncryption.S3_MANAGED,
            # NO website hosting - CloudFront lo manejará
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,  # Más seguro
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
    #========================IAM ROLE
        self.shared_layer = lambda_.LayerVersion(
            self, 'SharedLayer',
            layer_version_name='rekognition-poc-shared-layer',
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

        # 🆕 UPDATED VALIDATOR ROLE - Con permisos para invocar document indexer
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
                                's3:DeleteObject'  # 🆕 Para cleanup de documentos
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
                        ),
                        # 🆕 PERMISSION TO INVOKE DOCUMENT INDEXER
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'lambda:InvokeFunction'
                            ],
                            resources=[f'arn:aws:lambda:{self.region}:{self.account}:function:rekognition-poc-document-indexer']
                        )
                    ]
                )
            }
        )

        # 🆕 UPDATED API ROLE - Con permiso para bucket documents S3 HEAD
        self.api_role = iam.Role(
            self, 'ApiLambdaRole',
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
                                's3:HeadObject',  # 🆕 Para check-document-exists
                                's3:DeleteObject'  # 🆕 Para cleanup-document
                            ],
                            resources=[
                                f'{self.documents_bucket.bucket_arn}/*',
                                f'{self.user_photos_bucket.bucket_arn}/*'
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                's3:ListBucket'  # 🆕 Para check-document-exists
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
                            resources=[f'arn:aws:lambda:{self.region}:{self.account}:function:rekognition-poc-document-indexer']
                        ),
                        # 🆕 REKOGNITION PERMISSIONS FOR DOCUMENT INDEXER API
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                'rekognition:DetectFaces',
                                'rekognition:CreateCollection',
                                'rekognition:DescribeCollection'
                            ],
                            resources=['*']
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
            code=lambda_.Code.from_asset('functions/document_indexer'),
            role=self.indexer_role,
            timeout=Duration.minutes(5),
            memory_size=1024,
            layers=[
                self.shared_layer       
            ],
            environment={
                'COLLECTION_ID':'document-faces-collection',
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET':self.documents_bucket.bucket_name
            }
        )
        
        # 🆕 UPDATED USER VALIDATOR - Con nueva variable de entorno
        self.user_validator=lambda_.Function(
            self,'UserValidator',
            function_name='rekognition-poc-user-validator',
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
                'COLLECTION_ID':'document-faces-collection',
                'COMPARISON_RESULTS_TABLE':self.comparison_results_table.table_name,
                'INDEXED_DOCUMENTS_TABLE':self.indexed_documents_table.table_name,
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name,
                'USER_PHOTOS_BUCKET': self.user_photos_bucket.bucket_name,
                'DOCUMENT_INDEXER_FUNCTION': 'rekognition-poc-document-indexer'  # 🆕
            }
        )
#=======================================================================
#Lambdas para API
#======================================================================
        self.presigned_urls_lambda = lambda_.Function(
            self, 'PresignedUrlsLambda',
            function_name= 'rekognition-poc-presigned-urls',
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

        # 🆕 UPDATED Document indexer API - Con variables adicionales
        self.document_indexer_api = lambda_.Function(
            self, 'DocumentIndexerApi',
            function_name='rekognition-poc-document-indexer-api',
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('functions/document_indexer_api'),
            role=self.api_role,
            timeout=Duration.seconds(30),
            memory_size=256,
            layers=[
                self.shared_layer  # 🆕 Para DetectFaces inmediato
            ],
            environment={
                'DOCUMENT_INDEXER_FUNCTION': self.document_indexer.function_name,
                'DOCUMENTS_BUCKET': self.documents_bucket.bucket_name,
                'COLLECTION_ID': 'document-faces-collection'  # 🆕
            }
        )

        # Lambda para check validation (sin cambios)
        self.check_validation_lambda = lambda_.Function(
            self, 'CheckValidationLambda',
            function_name='rekognition-poc-check-validation',
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

        # 🆕 NEW LAMBDA: Check Document Exists
        self.check_document_exists_lambda = lambda_.Function(
            self, 'CheckDocumentExistsLambda',
            function_name='rekognition-poc-check-document-exists',
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

        # 🆕 NEW LAMBDA: Cleanup Document
        self.cleanup_document_lambda = lambda_.Function(
            self, 'CleanupDocumentLambda',
            function_name='rekognition-poc-cleanup-document',
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

# ======================================================================
# 🆕 CLOUDFRONT DISTRIBUTION - HTTPS Frontend
# ======================================================================
        # Crear Origin Access Identity para acceso seguro a S3
        self.origin_access_identity = cloudfront.OriginAccessIdentity(
            self, 'FrontendOAI',
            comment='OAI for Rekognition POC Frontend'
        )
        
        # Permitir que CloudFront acceda al bucket
        self.frontend_bucket.grant_read(self.origin_access_identity)

        # Crear distribución CloudFront
        self.distribution = cloudfront.Distribution(
            self, 'FrontendDistribution',
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
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,  # Solo US/EU para reducir costos
            comment='Rekognition POC Frontend Distribution'
        )

# ======================================================================
# 🆕 UPDATED API GATEWAY - Con nuevo endpoint
# ======================================================================
        self.api = apigateway.RestApi(
            self, 'RekognitionApi',
            rest_api_name='rekognition-poc-api',
            description='API for Rekognition POC Frontend',
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=apigateway.Cors.DEFAULT_HEADERS
            )
        )

        # Endpoints existentes
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

        # 🆕 NEW ENDPOINT: POST /check-document
        check_doc_resource = self.api.root.add_resource('check-document')
        check_doc_resource.add_method(
            'POST',
            apigateway.LambdaIntegration(self.check_document_exists_lambda)
        )

        # 🆕 NEW ENDPOINT: POST /cleanup-document
        cleanup_doc_resource = self.api.root.add_resource('cleanup-document')
        cleanup_doc_resource.add_method(
            'POST',
            apigateway.LambdaIntegration(self.cleanup_document_lambda)
        )

# ======================================================================
# S3 TRIGGERS (sin cambios)
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
# 🆕 FRONTEND DEPLOYMENT
# ======================================================================
        self.frontend_deployment = s3deploy.BucketDeployment(
            self, 'FrontendDeployment',
            sources=[s3deploy.Source.asset('frontend/dist')],
            destination_bucket=self.frontend_bucket,
            distribution=self.distribution,  # 🆕 Invalidar cache automáticamente
            distribution_paths=['/*'],  # 🆕 Invalidar todos los archivos
            retain_on_delete=False
        )       

# ======================================================================
# OUTPUTS - UPDATED
# ======================================================================
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
            self, 'FrontendBucketName',
            value=self.frontend_bucket.bucket_name,
            description='Bucket for frontend hosting'
        )
        
        # 🆕 NUEVA URL con HTTPS via CloudFront
        cdk.CfnOutput(
            self, 'FrontendUrl',
            value=f'https://{self.distribution.distribution_domain_name}',
            description='Frontend website URL (HTTPS via CloudFront)'
        )
        
        # 🆕 OUTPUT adicional para CloudFront
        cdk.CfnOutput(
            self, 'CloudFrontDistributionId',
            value=self.distribution.distribution_id,
            description='CloudFront distribution ID'
        )
        
        cdk.CfnOutput(
            self, 'ApiGatewayUrl',
            value=self.api.url,
            description='API Gateway endpoint URL'
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
        self._add_web_interface()

    def _add_web_interface(self):
        #S3 para hosting web
        self.web_bucket = s3.Bucket(
            self, 'WebInterfaceBucket',
            bucket_name=f'rekog-poc-web-{self.account}',
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,  # Mejor para cache invalidation
            removal_policy=RemovalPolicy.DESTROY,
            public_read_access=False,  # Explícitamente bloquear acceso público directo
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True  
            ),           
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD],
                    allowed_origins=['*'],
                    allowed_headers=['*'],
                    max_age=3000
                )
            ]
        )
        oai = cloudfront.OriginAccessIdentity(
            self, 'WebOAI',
            comment='OAI for Rekognition Web Interface'
        )
        self.web_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.CanonicalUserPrincipal(oai.cloud_front_origin_access_identity_s3_canonical_user_id)],
                actions=['s3:GetObject'],
                resources=[f'{self.web_bucket.bucket_arn}/*']
            )
        )
        self.web_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.CanonicalUserPrincipal(oai.cloud_front_origin_access_identity_s3_canonical_user_id)],
                actions=['s3:ListBucket'],
                resources=[self.web_bucket.bucket_arn]
            )
        )        
        self.distribution = cloudfront.Distribution(
            self, 'WebDistribution',
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(self.web_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED
            ),
            default_root_object='index.html',
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,  # Manejar 403 específicamente
                    response_http_status=200,
                    response_page_path='/index.html',
                    ttl=Duration.minutes(5)
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path='/index.html',
                    ttl=Duration.minutes(5)
                )
            ],
            comment='Rekognition POC Web Interface'
        )
        #API GATEWAY
        self.api = apigateway.RestApi(
            self, 'RekognitionWebAPI',
            rest_api_name='rekognition-poc-web-api',
            description='Web interface for Rekognition POC',
            binary_media_types=['image/*', 'application/octet-stream'],
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=[
                    'Content-Type',
                    'Authorization', 
                    'X-Amz-Date',
                    'X-Api-Key',
                    'X-Amz-Security-Token'
                ],
                max_age=Duration.seconds(3600)
            )
        )
        self._create_api_endpoints()
        self._deploy_web_files()
        cdk.CfnOutput(self,'WebBucketName',value=self.web_bucket.bucket_name)
        cdk.CfnOutput(self, 'APIGatewayURL',value=self.api.url)
        cdk.CfnOutput(
            self, 'WebInterfaceURL',
            value=f'https://{self.distribution.distribution_domain_name}',
            description='Web interface URL (CloudFront)'
        )
        cdk.CfnOutput(
            self, 'CloudFrontDistributionId',
            value=self.distribution.distribution_id,
            description='CloudFront Distribution ID for cache invalidation'
        )
    def _create_api_endpoints(self):
        #user endpoints
        users = self.api.root.add_resource('users')
        users.add_resource('lookup').add_method(
            'POST', 
            apigateway.LambdaIntegration(
                self.user_validator,
                proxy=True,
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code='200',
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': "'*'"
                        }
                    )
                ]
            ),
            method_responses=[
                apigateway.MethodResponse(
                    status_code='200',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ]
        )
        
        users.add_resource('validate').add_method(
            'POST',
            apigateway.LambdaIntegration(
                self.user_validator,
                proxy=True,
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code='200',
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': "'*'"
                        }
                    )
                ]
            ),
            method_responses=[
                apigateway.MethodResponse(
                    status_code='200',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ]
        )

        # Documents endpoints
        documents = self.api.root.add_resource('documents')
        documents.add_resource('index').add_method(
            'POST',
            apigateway.LambdaIntegration(
                self.document_indexer,
                proxy=True,
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code='200',
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': "'*'"
                        }
                    )
                ]
            ),
            method_responses=[
                apigateway.MethodResponse(
                    status_code='200',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ]
        )

        # Permisos explícitos para Lambda
        self.user_validator.add_permission(
            'AllowAPIGatewayInvoke',
            principal=iam.ServicePrincipal('apigateway.amazonaws.com'),
            action='lambda:InvokeFunction',
            source_arn=f"{self.api.arn_for_execute_api()}/*/*"
        )
        
        self.document_indexer.add_permission(
            'AllowAPIGatewayInvokeIndexer',
            principal=iam.ServicePrincipal('apigateway.amazonaws.com'),
            action='lambda:InvokeFunction',
            source_arn=f"{self.api.arn_for_execute_api()}/*/*"
        )
    def _deploy_web_files(self):
        """Deploy automático de archivos web (placeholder por ahora)"""
        # Esta funcionalidad se manejará manualmente con scripts/web_config.py
        # para evitar complejidad adicional en CDK
        pass


















                                        






















