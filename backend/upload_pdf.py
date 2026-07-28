import requests
import json

url = "http://127.0.0.1:8000/api/ingest/upload?user_id=default"
pdf_path = "Google_Cloud_Professional_Cloud_Architect.pdf"

with open(pdf_path, "rb") as f:
    response = requests.post(url, files={"file": (pdf_path, f)})

print("=== PDF INGESTION RESPONSE ===")
print("Status Code:", response.status_code)
print(json.dumps(response.json(), indent=2))
