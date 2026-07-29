import asyncio
import sqlite3
from app.core.vectordb.embeddings import EmbeddingService
from app.core.vectordb.client import ChromaClient

async def main():
    conn = sqlite3.connect("chroma_db/chroma.sqlite3")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, string_value
        FROM embedding_metadata
        WHERE key='chroma:document' AND id IN (5, 6, 7, 8, 9, 10, 11)
    """)
    rows = cursor.fetchall()
    conn.close()

    resume_text = "\n\n".join([r[1] for r in rows])
    print(f"Extracted resume text ({len(resume_text)} chars):")
    print(resume_text[:200] + "...")

    # Create RawDocument-like structure
    class CustomDoc:
        filename = "Yogesh_Bhangale_Resume.pdf"
        text = resume_text
        file_type = type("FT", (), {"value": "pdf"})()
        file_id = "yogesh_resume_001"

    svc = EmbeddingService()
    count = await svc.store_raw_chunks(CustomDoc(), user_id="default", file_id="yogesh_resume_001")
    print(f"Successfully re-stored {count} chunks for Yogesh_Bhangale_Resume.pdf with formatted headers.")

if __name__ == "__main__":
    asyncio.run(main())
