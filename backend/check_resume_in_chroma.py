from app.core.vectordb.client import ChromaClient

chroma = ChromaClient()

print("=== CHROMADB DIRECT AUDIT FOR RESUME DOCUMENTS ===")

target_terms = ["resume", "bhangale", "yogesh"]

collections = ["raw_chunks", "skills", "projects", "certifications", "internships", "achievements", "academics"]

total_found = 0

for col_name in collections:
    col = chroma.get_collection(col_name)
    data = col.get()
    
    ids = data.get("ids", [])
    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])
    
    matched_in_col = 0
    for doc_id, doc_text, meta in zip(ids, documents, metadatas):
        doc_str = (doc_text or "").lower()
        meta_str = str(meta or {}).lower()
        
        if any(term in doc_str or term in meta_str for term in target_terms):
            matched_in_col += 1
            total_found += 1
            print(f"\n[MATCH in '{col_name}'] ID: {doc_id}")
            print(f"  Metadata: {meta}")
            print(f"  Snippet : {(doc_text or '')[:150]}...")

    print(f"Collection '{col_name}': {matched_in_col} matches out of {len(ids)} items.")

print(f"\nTOTAL RESUME MATCHES IN CHROMADB: {total_found}")
