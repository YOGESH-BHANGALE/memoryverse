import sqlite3

conn = sqlite3.connect("chroma_db/chroma.sqlite3")
cursor = conn.cursor()

print("=== CHECKING USER_ID FOR YOGESH_BHANGALE_RESUME ===")
cursor.execute("""
    SELECT id, key, string_value
    FROM embedding_metadata
    WHERE string_value LIKE '%Yogesh_Bhangale_Resume%'
""")
matches = cursor.fetchall()
for m in matches:
    doc_id = m[0]
    cursor.execute("SELECT key, string_value FROM embedding_metadata WHERE id=?", (doc_id,))
    all_meta = cursor.fetchall()
    print(f"\nEmbedding ID: {doc_id}")
    for k, v in all_meta:
        print(f"  {k} = {v}")

conn.close()
