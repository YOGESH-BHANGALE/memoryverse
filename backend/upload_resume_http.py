import requests

with open("Yogesh_Bhangale_Resume.txt", "rb") as f:
    res = requests.post("http://127.0.0.1:8000/api/ingest/upload?user_id=default", files={"file": f})

print("Upload Status:", res.status_code)
print("Response:", res.text)
