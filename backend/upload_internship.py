import requests, json

with open("Acme_Corp_Internship_Offer.pdf", "rb") as f:
    r = requests.post(
        "http://127.0.0.1:8000/api/ingest/upload?user_id=default",
        files={"file": ("Acme_Corp_Internship_Offer.pdf", f, "application/pdf")},
    )

print(f"Status: {r.status_code}")
data = r.json()
print(f"Entities extracted: {data['entities_extracted']}")
for e in data["entities"]:
    print(f"  [{e['category']}] {e['title']}")
    for k, v in e.get("data", {}).items():
        if v:
            print(f"      {k}: {v}")
