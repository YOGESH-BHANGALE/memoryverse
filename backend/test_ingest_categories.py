import requests
import json

def test_upload(file_path):
    print(f"\n==================================================")
    print(f"TESTING UPLOAD: {file_path}")
    print(f"==================================================")
    with open(file_path, "rb") as f:
        files = {"file": f}
        res = requests.post("http://127.0.0.1:8000/api/ingest/upload?user_id=test_category_user", files=files)
    
    if res.status_code == 200:
        data = res.json()
        entities = data.get("entities", [])
        print(f"SUCCESS: Extracted {len(entities)} entities from {file_path}:")
        
        category_counts = {}
        for e in entities:
            cat = e.get("category")
            title = e.get("title")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            print(f"  - [{cat}] {title}")
            
        print("\nCATEGORY SUMMARY:")
        for cat, count in category_counts.items():
            print(f"  - {cat}: {count}")
    else:
        print(f"UPLOAD FAILED ({res.status_code}): {res.text}")

test_upload("Distributed_Stream_Processor_Project_Report.txt")
test_upload("Academic_Degree_Transcript_XYZ_University.txt")
