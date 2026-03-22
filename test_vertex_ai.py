import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def test_vertex_ai():
    # Ensure you are authenticated via 'gcloud auth application-default login'
    # Or have GOOGLE_APPLICATION_CREDENTIALS pointing to a valid service account JSON
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if not project_id:
        print("Error: GOOGLE_CLOUD_PROJECT environment variable is not set.")
        print("Please set your Google Cloud project ID using: set GOOGLE_CLOUD_PROJECT=your_project_id")
        return
    
    print(f"Initializing client for Vertex AI (Project: {project_id}, Location: {location})...")
    
    try:
        # Vertex AI usage requires setting vertexai=True, 
        # and providing the GCP project and location.
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )
        
        print("Generating response...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Explain what Vertex AI is in one short sentence.'
        )
        print("\n--- Response ---")
        print(response.text)
        print("----------------")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        print("Make sure you are authenticated to Google Cloud (run `gcloud auth application-default login`).")

if __name__ == "__main__":
    test_vertex_ai()
