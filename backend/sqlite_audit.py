import sqlite3

conn = sqlite3.connect("chroma_db/chroma.sqlite3")
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print("SQLite Tables:", tables)

# Search embedding_metadata and embedding_fulltext
print("\n=== SEARCHING METADATA FOR 'RESUME' / 'BHANGALE' / 'YOGESH' ===")
cursor.execute("""
    SELECT string_value, int_value, float_value, key, id 
    FROM embedding_metadata 
    WHERE string_value LIKE '%resume%' 
       OR string_value LIKE '%bhangale%' 
       OR string_value LIKE '%yogesh%'
       OR key LIKE '%resume%'
""")
matches = cursor.fetchall()
print(f"Total Metadata Matches Found: {len(matches)}")
for m in matches:
    print("  Match:", m)

# Search raw string text in embeddings table if any
cursor.execute("""
    SELECT id, document 
    FROM embedding_fulltext 
    WHERE document LIKE '%resume%' 
       OR document LIKE '%bhangale%' 
       OR document LIKE '%yogesh%'
""")
text_matches = cursor.fetchall()
print(f"\nTotal Fulltext Matches Found: {len(text_matches)}")
for t in text_matches:
    print("  Fulltext Match ID:", t[0], "Snippet:", t[1][:100])

conn.close()
