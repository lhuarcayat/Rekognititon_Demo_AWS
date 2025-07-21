class VerificationService {
  constructor() {
    this.apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:3001';
  }

  async createLivenessSession() {
    try {
      const response = await fetch(`${this.apiUrl}/api/create-liveness-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error creating liveness session:', error);
      throw error;
    }
  }

  async compareWithDocument(documentImage, sessionId) {
    try {
      const formData = new FormData();
      formData.append('documentImage', documentImage);
      formData.append('sessionId', sessionId);

      const response = await fetch(`${this.apiUrl}/api/compare-identity`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error comparing identity:', error);
      throw error;
    }
  }
}

export const verificationService = new VerificationService();