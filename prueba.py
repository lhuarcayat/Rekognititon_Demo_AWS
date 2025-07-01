import boto3
from botocore.exceptions import ClientError

def listar_colecciones():
    client = boto3.client('rekognition')

    try:
        response = client.list_collections()
        colecciones = response['CollectionIds']

        if not colecciones:
            print("🔍 No tienes colecciones registradas.")
        else:
            print("📋 Colecciones disponibles:")
            for idx, cid in enumerate(colecciones, 1):
                print(f"  {idx}. {cid}")

    except ClientError as e:
        print(f"❌ Error: {e.response['Error']['Message']}")

listar_colecciones()

def describe_collection(collection_id):
    client=boto3.client('rekognition')
    try:
        response=client.describe_collection(CollectionId=collection_id)
        
        print("📁 Metadatos de la colección:")
        print(f"  - CollectionId: {response['CollectionARN'].split('/')[-1]}")
        print(f"  - ARN: {response['CollectionARN']}")
        print(f"  - Rostros indexados: {response['FaceCount']}")
        print(f"  - Fecha de creación: {response['CreationTimestamp']}")
        print(f"  - Versión del modelo: {response['FaceModelVersion']}")

    except ClientError as e:
        print(f"❌ Error: {e.response['Error']['Message']}")

# Cambia este valor por el ID de tu colección
mi_coleccion = "document-faces-collection"

describe_collection(mi_coleccion)

def listar_rostros(coleccion_id):
    client = boto3.client('rekognition')

    try:
        print(f"📂 Rostros en la colección '{coleccion_id}':")
        token = None

        while True:
            if token:
                response = client.list_faces(CollectionId=coleccion_id, NextToken=token)
            else:
                response = client.list_faces(CollectionId=coleccion_id)

            for face in response['Faces']:
                print("🧑‍💼 Rostro:")
                print(f"  - FaceId: {face['FaceId']}")
                print(f"  - ImageId: {face['ImageId']}")
                print(f"  - ExternalImageId: {face.get('ExternalImageId', 'N/A')}")
                print(f"  - Confidence: {face['Confidence']:.2f}")
                print(f"  - BoundingBox: {face['BoundingBox']}")
                print("---")

            token = response.get('NextToken')
            if not token:
                break

    except ClientError as e:
        print(f"❌ Error: {e.response['Error']['Message']}")

# Cambia esto por el ID de tu colección
coleccion = "document-faces-collection"
listar_rostros(coleccion)