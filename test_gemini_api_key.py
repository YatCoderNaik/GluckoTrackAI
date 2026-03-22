import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def test_gemini_api():
    # Make sure to set GEMINI_API_KEY environment variable
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        print("Please set it using: set GEMINI_API_KEY=your_key")
        return

    print("Initializing client via Gemini API Key...")
    client = genai.Client(api_key=api_key)

    try:
        print("Generating response...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='How is the weather in Bangalore during the month of March?'
        )
        print("\n--- Response ---")
        print(response.text)
        print("----------------")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    test_gemini_api()
