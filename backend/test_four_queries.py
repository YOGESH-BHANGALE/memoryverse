import requests
import json

queries = [
    "Show all my certificates",
    "Show my internship documents",
    "Show my latest resume",
    "Show my AI projects"
]

out_lines = ["=== BACKEND RAG QUERY AUDIT ==="]

for q in queries:
    payload = {
        "query": q,
        "user_id": "default",
        "top_k": 10,
        "use_mmr": True,
        "stream": False
    }
    try:
        res = requests.post("http://127.0.0.1:8000/api/search/query", json=payload, timeout=20)
        if res.status_code == 200:
            data = res.json()
            out_lines.append(f"\nQUERY: '{q}'")
            out_lines.append("ANSWER:\n" + data.get("answer", ""))
            sources = data.get("sources", [])
            out_lines.append(f"SOURCES RETURNED ({len(sources)}):")
            for s in sources:
                out_lines.append(f"  - [{s.get('category')}] {s.get('title')} (score: {s.get('score'):.2f}, file_id: {s.get('file_id')})")
        else:
            out_lines.append(f"\nFAILED for '{q}': {res.status_code} {res.text}")
    except Exception as e:
        out_lines.append(f"\nEXCEPTION for '{q}': {e}")

output_text = "\n".join(out_lines)
with open("query_audit_results.txt", "w", encoding="utf-8") as f:
    f.write(output_text)

print("Audit finished. Results written to query_audit_results.txt.")
