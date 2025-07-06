import boto3

rekognition = boto3.client('rekognition')
response = rekognition.list_collections()
print("Colecciones:")

for collection_id in response['CollectionIds']:
    print(f"- {collection_id}")