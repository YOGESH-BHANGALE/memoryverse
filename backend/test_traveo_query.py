import requests

payload = {
    "query": "What projects did I build?",
    "user_id": "default",
    "top_k": 10,
    "use_mmr": True,
    "stream": False
}

res = requests.post("http://127.0.0.1:8000/api/search/query", json=payload)
if res.status_code == 200:
    data = res.json()
    out = ["=== QUERY RESULT: 'What projects did I build?' ==="]
    out.append("\nANSWER:\n" + data.get("answer", ""))
    out.append("\nSOURCES:")
    for s in data.get("sources", []):
        out.append(f"  - [{s.get('category')}] {s.get('title')} (score: {s.get('score'):.2f}, file_id: {s.get('file_id')})")
    
    with open("traveo_query_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("Result saved to traveo_query_result.txt")
else:
    print(f"Query Failed: {res.status_code} {res.text}")
