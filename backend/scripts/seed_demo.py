import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import ExtractionResult, Project, Skill, Certification, Internship, Achievement, Academic
from app.core.ingestion.categorizer import Categorizer
from app.core.vectordb.embeddings import EmbeddingService
from app.core.vectordb.relations import RelationshipEngine
from app.utils.logger import logger

# A fixed, non-"default" demo identity. The frontend ignores the literal
# "default" and mints a random UUID, so anything seeded under "default" is
# unreachable in the UI. Seeding under a real id — and printing the URL that
# pins it (?user=<id>) — makes this script a working one-command demo setup.
DEFAULT_DEMO_USER = "11111111-1111-4111-8111-111111111111"
FRONTEND_ORIGIN = os.getenv("MEMORYVERSE_FRONTEND_ORIGIN", "http://localhost:3001")


async def seed(user_id: str):
    print(f"Seeding demo data under user_id={user_id} ...")
    extraction = ExtractionResult(
        certifications=[
            Certification(name="AWS Certified Solutions Architect", issuer="Amazon Web Services", date="2024-05", credential_id="AWS-1234")
        ],
        skills=[
            Skill(name="Python", category="Programming Language", level="Advanced"),
            Skill(name="React", category="Frontend", level="Advanced"),
            Skill(name="FastAPI", category="Backend", level="Intermediate"),
            Skill(name="Vector Databases", category="Data Science", level="Intermediate")
        ],
        projects=[
            Project(
                name="AI Digital Identity System", 
                description="Built an intelligent knowledge repository using FastAPI, Next.js, and ChromaDB.", 
                tech_stack=["Python", "FastAPI", "React", "Vector Databases", "OpenAI"],
                date_range="2025-01 - 2025-06",
                url="https://github.com/demo/digital-identity"
            ),
            Project(
                name="Traveo — Ride Sharing Application", 
                description="Developed a ride-sharing platform that connects users traveling to similar destinations using MEAN Stack and JWT Authentication.", 
                tech_stack=["MongoDB", "Express.js", "Angular", "Node.js", "JWT Authentication"],
                date_range="2024-01 - 2024-05",
                url="https://github.com/YOGESH-BHANGALE/traveo"
            ),
            Project(
                name="E-Commerce Platform", 
                description="Full-stack marketplace with Stripe integration.", 
                tech_stack=["React", "Node.js", "MongoDB"],
                date_range="2023-09 - 2023-12",
                url="https://github.com/demo/ecommerce"
            )
        ],
        internships=[
            Internship(
                role="Software Engineering Intern",
                company="Google",
                start_date="2024-05",
                end_date="2024-08",
                description="Developed internal tools using Python and React."
            )
        ],
        achievements=[
            Achievement(
                title="First Place - Global AI Hackathon",
                date="2025-03",
                description="Won first place out of 500 teams for building an AI knowledge system.",
                impact="Received $10k grant."
            )
        ],
        academics=[
            Academic(
                institution="Stanford University",
                degree="B.S. Computer Science",
                start_date="2021-09",
                end_date="2025-06",
                description="Focus on Artificial Intelligence. GPA: 3.9"
            )
        ]
    )

    categorizer = Categorizer()
    entities = categorizer.categorise(extraction)
    print(f"Categorized {len(entities)} entities.")

    embedding_svc = EmbeddingService()
    await embedding_svc.store_entities(entities, user_id)
    print("Stored embeddings in ChromaDB.")

    relation_engine = RelationshipEngine()
    graph = relation_engine.rebuild_user_graph(user_id)
    edge_count = len(getattr(graph, "edges", []) or [])
    print(f"Built and cached the knowledge graph ({edge_count} edges).")
    print("Done!")
    print("\nOpen the demo (this URL pins the seeded user automatically):")
    print(f"  {FRONTEND_ORIGIN}/dashboard?user={user_id}")

if __name__ == "__main__":
    uid = (
        sys.argv[1] if len(sys.argv) > 1
        else os.getenv("MEMORYVERSE_DEMO_USER") or DEFAULT_DEMO_USER
    )
    if uid == "default":
        print("Refusing to seed under 'default' — the frontend ignores it and the UI would look empty.")
        print(f"Pass a real id, e.g.:  python scripts/seed_demo.py {DEFAULT_DEMO_USER}")
        sys.exit(1)
    asyncio.run(seed(uid))
