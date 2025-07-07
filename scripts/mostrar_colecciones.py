import boto3

# Crear cliente Rekognition
rekognition = boto3.client('rekognition')

# Listar colecciones disponibles
response = rekognition.list_collections()
collection_ids = response['CollectionIds']

print("Colecciones disponibles:")
for idx, collection_id in enumerate(collection_ids, 1):
    print(f"{idx}. {collection_id}")

# Elegir una colección específica (ejemplo: primera de la lista)
if not collection_ids:
    print("No se encontraron colecciones.")
    exit()

selected_collection = collection_ids[4]  # puedes cambiar el índice si deseas otra

print(f"\nMostrando rostros de la colección: {selected_collection}")

# Listar rostros dentro de la colección
faces_response = rekognition.list_faces(CollectionId=selected_collection)

while True:
    for face in faces_response['Faces']:
        print(f"- FaceId: {face['FaceId']}, ImageId: {face['ImageId']}")

    # Paginación si hay más resultados
    if 'NextToken' in faces_response:
        faces_response = rekognition.list_faces(
            CollectionId=selected_collection,
            NextToken=faces_response['NextToken']
        )
    else:
        break
