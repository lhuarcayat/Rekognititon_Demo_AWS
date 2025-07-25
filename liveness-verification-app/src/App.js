import React, { useState } from 'react';
import {Authenticator} from '@aws-amplify/ui-react';
import DocumentUpload from './components/DocumentUpload';
import LivenessCheck from './components/LivenessCheck';
import VerificationResult from './components/VerificationResult';
import {Alert} from '@aws-amplify/ui-react';

function App(){
  const [step, setStep] = useState('upload');
  const [documentImage, setDocumentImage] = useState(null);
  const [verificationResult, setVerificationResult] = useState(null);
  const [error, setError] = useState(null);

  const handleDocumentUpload = (imageFile) => {
    setDocumentImage(imageFile);
    setStep('liveness');
    setError(null);
  };

  const handleLivenessComplete = (result) => {
    setVerificationResult(result);
    setStep('result');
  };

  const handleError = (errorMessage) => {
    setError(errorMessage);
  };

  const resetVerification = () => {
    setStep('upload');
    setDocumentImage(null);
    setVerificationResult(null);
    setError(null);
  }
  return (
    <div className = 'app-container'>
      <header className = 'app-header'>
        <h1> Verificación de Identidad</h1>
        <p>Sistema de verificación facial con documento</p>
      </header>

      <main className = 'app-main'>
        {error && (
          <Alert variation='error' hasIcon={true} className = 'error-alert'>
            {error}
          </Alert>
        )}
        {step == 'upload' && (
          <DocumentUpload
            onUpload = {handleDocumentUpload}
            onError = {handleError}
          />
        )}

        {step == 'liveness' && (
          <LivenessCheck
            documentImage = {documentImage}
            onComplete = {handleLivenessComplete}
            onError = {handleError}
          />
        )}
        
        {step == 'result' && (
          <VerificationResult
            result = {verificationResult}
            onReset = {resetVerification}
          />
        )}
       
        
        
        


      </main>
    </div>
  );
}

export default App;