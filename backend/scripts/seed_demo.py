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

async def seed():
    print("Seeding demo data...")
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
    await embedding_svc.store_entities(entities, "default")
    print("Stored embeddings in ChromaDB.")

    relation_engine = RelationshipEngine()
    relations = relation_engine.build_relations(entities)
    relation_engine.store_relations(entities, relations)
    print(f"Stored {len(relations)} relations.")
    print("Done!")

if __name__ == "__main__":
    asyncio.run(seed())
