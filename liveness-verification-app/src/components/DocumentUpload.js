import React, { useState } from 'react';
import { Button, Card, Text, Image, View } from '@aws-amplify/ui-react';

function DocumentUpload({ onUpload, onError }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [preview, setPreview] = useState(null);

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    
    if (!file) return;

    // Validar tipo de archivo
    if (!file.type.startsWith('image/')) {
      onError('Por favor selecciona un archivo de imagen válido');
      return;
    }

    // Validar tamaño (5MB máximo)
    if (file.size > 5 * 1024 * 1024) {
      onError('La imagen debe ser menor a 5MB');
      return;
    }

    setSelectedFile(file);

    // Generar preview
    const reader = new FileReader();
    reader.onload = (e) => setPreview(e.target.result);
    reader.readAsDataURL(file);
  };

  const handleUpload = () => {
    if (!selectedFile) {
      onError('Por favor selecciona una imagen de tu documento');
      return;
    }

    onUpload(selectedFile);
  };

  return (
    <Card className="upload-card">
      <Text fontSize="xl" fontWeight="bold" marginBottom="20px">
        Paso 1: Sube tu documento de identidad
      </Text>
      
      <Text marginBottom="20px" color="gray">
        Asegúrate de que la foto sea clara y que se vea completamente tu rostro
      </Text>

      <View className="file-upload-container">
        <input
          type="file"
          accept="image/*"
          onChange={handleFileSelect}
          className="file-input"
          id="document-upload"
        />
        <label htmlFor="document-upload" className="file-label">
          📄 Seleccionar imagen del documento
        </label>
      </View>

      {preview && (
        <View className="preview-container">
          <Text fontWeight="bold" marginBottom="10px">Vista previa:</Text>
          <Image
            src={preview}
            alt="Preview del documento"
            className="preview-image"
          />
        </View>
      )}

      <Button
        onClick={handleUpload}
        disabled={!selectedFile}
        variation="primary"
        size="large"
        className="continue-button"
      >
        Continuar a verificación facial →
      </Button>
    </Card>
  );
}

export default DocumentUpload;