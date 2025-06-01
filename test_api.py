import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000/upload"
# This ensures the script can find your sample_inputs folder
# regardless of which directory you run the script from within the project.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SAMPLE_INPUTS_DIR = os.path.join(PROJECT_ROOT, "sample_inputs")

def print_response_details(response, test_name):
    """Helper function to print response details in a consistent format."""
    print(f"\n--- {test_name} Result ---")
    print(f"Status Code: {response.status_code}")

    try:
        response_json = response.json()

        # Extract the audit_log content
        audit_log_content = response_json.get('audit_log', 'Audit log not found in response.')

        # Remove audit_log from the main JSON structure for cleaner printing
        # Make a copy to avoid modifying the original response_json if it's used elsewhere
        response_to_print = response_json.copy()
        if 'audit_log' in response_to_print:
            del response_to_print['audit_log']

        print("Response Body (Excluding Detailed Audit Log):")
        print(json.dumps(response_to_print, indent=2))

        # Print the audit_log separately, line by line
        print("\n--- Detailed Audit Log ---")
        print(audit_log_content) # Python's print() function will correctly interpret '\n' as newlines
        print("----------------------------")

    except json.JSONDecodeError:
        print("Could not decode JSON response. Raw text:")
        print(response.text)
    except Exception as e:
        print(f"An unexpected error occurred while processing response: {e}")

def test_email_file_upload():
    print("\n--- Starting Email File Upload (email_sample.eml) ---")
    file_name = "email_sample.eml"
    file_path = os.path.join(SAMPLE_INPUTS_DIR, file_name)

    if not os.path.exists(file_path):
        print(f"ERROR: Email file not found at {file_path}. Please ensure it exists in the 'sample_inputs' folder.")
        return

    try:
        with open(file_path, "rb") as f:
            files = {'file': (file_name, f, 'message/rfc822')}
            headers = {'accept': 'application/json'}

            print(f"Attempting to upload {file_name} to {BASE_URL}...")
            response = requests.post(BASE_URL, files=files, headers=headers)
        
        print_response_details(response, "Email File Upload Test")

    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Could not connect to the server at {BASE_URL}. Is your FastAPI app running?")
        print(f"Connection Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Email File Upload: {e}")


def test_json_data_upload():
    print("\n--- Starting JSON Data Upload (json_sample_fraud.json) ---")
    json_file_name = "json_sample_fraud.json"
    json_file_path = os.path.join(SAMPLE_INPUTS_DIR, json_file_name)

    if not os.path.exists(json_file_path):
        print(f"ERROR: JSON file not found at {json_file_path}. Please ensure it exists in the 'sample_inputs' folder.")
        return

    try:
        with open(json_file_path, "r") as f:
            json_content = f.read()

        # FastAPI expects this as a Form field for `json_data: Optional[str] = Form(None)`
        data = {'json_data': json_content}
        headers = {'accept': 'application/json'}

        print(f"Attempting to upload {json_file_name} as raw JSON string to {BASE_URL}...")
        response = requests.post(BASE_URL, data=data, headers=headers) # Use data= for form-urlencoded

        print_response_details(response, "JSON Data Upload Test")

    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Could not connect to the server at {BASE_URL}. Is your FastAPI app running?")
        print(f"Connection Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during JSON Data Upload: {e}")

def test_pdf_invoice_upload():
    print("\n--- Starting PDF Invoice Upload (pdf_invoice_sample.pdf) ---")
    file_name = "pdf_invoice_sample.pdf"
    file_path = os.path.join(SAMPLE_INPUTS_DIR, file_name)

    if not os.path.exists(file_path):
        print(f"ERROR: PDF file not found at {file_path}. Please ensure it exists in the 'sample_inputs' folder.")
        return

    try:
        with open(file_path, "rb") as f:
            files = {'file': (file_name, f, 'application/pdf')}
            headers = {'accept': 'application/json'}

            print(f"Attempting to upload {file_name} to {BASE_URL}...")
            response = requests.post(BASE_URL, files=files, headers=headers)
        
        print_response_details(response, "PDF Invoice Upload Test")

    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Could not connect to the server at {BASE_URL}. Is your FastAPI app running?")
        print(f"Connection Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during PDF Invoice Upload: {e}")

# --- NEW FUNCTION FOR PDF REGULATION ---
def test_pdf_regulation_upload():
    print("\n--- Starting PDF Regulation Upload (pdf_regulation_sample.pdf) ---")
    file_name = "pdf_regulation_sample.pdf"
    file_path = os.path.join(SAMPLE_INPUTS_DIR, file_name)

    if not os.path.exists(file_path):
        print(f"ERROR: PDF regulation file not found at {file_path}. Please ensure it exists in the 'sample_inputs' folder.")
        return

    try:
        with open(file_path, "rb") as f:
            files = {'file': (file_name, f, 'application/pdf')}
            headers = {'accept': 'application/json'}

            print(f"Attempting to upload {file_name} to {BASE_URL}...")
            response = requests.post(BASE_URL, files=files, headers=headers)
        
        print_response_details(response, "PDF Regulation Upload Test")

    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Could not connect to the server at {BASE_URL}. Is your FastAPI app running?")
        print(f"Connection Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during PDF Regulation Upload: {e}")


# --- Main Execution Block ---
if __name__ == "__main__":
    # --- IMPORTANT CHECKLIST BEFORE RUNNING ---
    # 1. Ensure your FastAPI application is running in a separate VS Code terminal.
    #    It should be started with:
    #    $env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY" ; uvicorn main:app --reload
    # 2. Ensure you have 'requests' installed: pip install requests
    # 3. Ensure the 'sample_inputs' folder and ALL required files (.eml, .json, .pdf)
    #    exist in the same directory as this 'test_api.py' script.
    #    The structure should be:
    #    FLOWBIT_AI_SYSTEM/
    #    ├── sample_inputs/
    #    │   ├── email_sample.eml
    #    │   ├── json_sample_fraud.json
    #    │   ├── pdf_invoice_sample.pdf
    #    │   └── pdf_regulation_sample.pdf  <-- Make sure this file exists!
    #    ├── test_api.py
    #    └── ... (other project files)

    print("--- Starting All Agent Tests ---")
    test_email_file_upload()
    test_json_data_upload()
    test_pdf_invoice_upload()
    test_pdf_regulation_upload() # <-- Now calling the new test function!
    print("\n--- All Agent Tests Completed ---")