import React from 'react';
import ReactDOM from 'react-dom/client';
import { Amplify } from 'aws-amplify';
//import { awsConfig} from './config/aws-config';
import App from './App';
import '@aws-amplify/ui-react/styles.css';
import './App.css';

const amplifyConfig = {
  Auth: {
    Cognito: {
      region: 'us-east-1',
      identityPoolId: 'us-east-1:5faa0404-5baa-4f4e-904a-09d3c998f2c2',
      allowGuestAccess: true
    }
  },
  aws_project_region: 'us-east-1',
  aws_cognito_region: 'us-east-1',
  aws_cognito_identity_pool_id: 'us-east-1:5faa0404-5baa-4f4e-904a-09d3c998f2c2'
};




//Amplify.configure(awsConfig);
Amplify.configure(amplifyConfig);

console.log('Amplify configurado:', amplifyConfig);

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
