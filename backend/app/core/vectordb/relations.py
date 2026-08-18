"""
Relationship Engine — builds an explainable, cross-document knowledge graph.

Every edge carries *evidence*: the concrete reason two entities are linked
(a shared technology, a name match, an overlapping date window, a career
signal). That is the difference between a knowledge map and a list of nearest
vector neighbours — a reviewer can click any connection and see why it exists.

Chains modelled here:

    Certification ──certifies────> Skill
    Skill ─────────used_in───────> Project
    Project ───────built_during──> Internship
    Internship ────leads_to──────> Career Path   (derived node)
    Internship ────developed─────> Skill
    Project ───────recognised_by─> Achievement
    Academics ─────taught────────> Skill

Two earlier limitations are fixed:

1. Relations were only ever computed over *one upload's* entities, so a demo
   of three documents produced three disconnected islands. The graph is now
   built over the user's whole corpus, read back out of Chroma
   (:meth:`RelationshipEngine.rebuild_user_graph`).
2. Only 3 of the 6 declared relation types were actually implemented —
   Certification→Skill and Internship→Career Path did not exist at all.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any, Iterable

from app.core.vectordb.client import COLLECTIONS, ChromaClient, collection_for_category
from app.models.entities import document_to_entity
from app.models.schemas import (
    CategorisedEntity,
    EntityCategory,
    EntityConnectionsResponse,
    EntityRelation,
    GraphNode,
    KnowledgeGraphResponse,
    RelationEvidence,
)
from app.utils.logger import logger

CAREER_PATH_CATEGORY = "career_path"

# (source category, target category) -> relation type
RELATION_TYPES: dict[tuple[str, str], str] = {
    ("certification", "skill"): "certifies",
    ("skill", "project"): "used_in",
    ("internship", "skill"): "developed",
    ("project", "internship"): "built_during",
    ("internship", CAREER_PATH_CATEGORY): "leads_to",
    ("project", "achievement"): "recognised_by",
    ("academics", "skill"): "taught",
}

# Human-readable gloss per relation type — powers the graph legend.
RELATION_LABELS: dict[str, str] = {
    "certifies": "Certification proves a skill",
    "used_in": "Skill applied in a project",
    "developed": "Internship developed a skill",
    "built_during": "Project overlaps an internship",
    "leads_to": "Experience points to a career path",
    "recognised_by": "Project recognised by an achievement",
    "taught": "Studies taught a skill",
}

# Graph cache is module-level because ``get_relation_engine()`` hands out a
# fresh RelationshipEngine per request; an instance attribute would never hit.
_GRAPH_CACHE: dict[str, KnowledgeGraphResponse] = {}


# ── Text matching ───────────────────────────────────────────────────────

# "+" and "#" survive normalisation so "C++" and "C#" stay distinguishable.
_PUNCT_RE = re.compile(r"[^a-z0-9+#]+")


def _norm(text: Any) -> str:
    """Lowercase and collapse punctuation to single spaces: 'Node.js' -> 'node js'."""
    return _PUNCT_RE.sub(" ", str(text or "").lower()).strip()


# Spellings the same technology arrives under. A skill listed as "JS" must
# still match a project whose tech stack says "JavaScript".
_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("javascript", "js", "ecmascript"),
    ("typescript", "ts"),
    ("python", "py"),
    ("machine learning", "ml"),
    ("artificial intelligence", "ai"),
    ("deep learning", "dl"),
    ("natural language processing", "nlp"),
    ("large language model", "llm", "llms"),
    ("node js", "nodejs", "node"),
    ("express js", "expressjs", "express"),
    ("react", "react js", "reactjs"),
    ("next js", "nextjs"),
    ("postgresql", "postgres", "psql"),
    ("mongodb", "mongo"),
    ("kubernetes", "k8s"),
    ("amazon web services", "aws"),
    ("google cloud platform", "gcp", "google cloud"),
    ("microsoft azure", "azure"),
    ("structured query language", "sql"),
    ("c++", "cpp", "c plus plus"),
    ("c#", "csharp", "c sharp"),
    ("data structures and algorithms", "dsa"),
    ("scikit learn", "sklearn", "scikit"),
    ("power bi", "powerbi"),
    ("html", "html5"),
    ("css", "css3"),
    ("internet of things", "iot"),
    ("raspberry pi", "raspberrypi"),
    ("continuous integration continuous deployment", "ci cd", "cicd"),
)


@lru_cache(maxsize=4096)
def _variants(term: str) -> tuple[str, ...]:
    """Every spelling of ``term``, longest first so evidence quotes the best match."""
    base = _norm(term)
    if not base:
        return ()
    out = {base}
    for group in _ALIAS_GROUPS:
        if base in group:
            out.update(group)
    # Two characters is the floor: "ai"/"ml"/"js" are meaningful tokens, while
    # single letters ("C", "R") match far too much free text to be safe here.
    return tuple(sorted((v for v in out if len(v) >= 2), key=len, reverse=True))


@lru_cache(maxsize=4096)
def _patterns(term: str) -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Compiled whole-token patterns for each spelling of ``term``."""
    return tuple(
        (v, re.compile(rf"(?<![a-z0-9+#]){re.escape(v)}(?![a-z0-9+#])"))
        for v in _variants(term)
    )


def _find_in_norm(haystack_norm: str, term: str) -> str | None:
    """Return the matched spelling of ``term`` inside already-normalised text."""
    if not haystack_norm:
        return None
    for variant, pattern in _patterns(term):
        if pattern.search(haystack_norm):
            return variant
    return None


def _find(haystack: Any, term: str) -> str | None:
    """Return the matched spelling of ``term`` inside ``haystack``, else None."""
    return _find_in_norm(_norm(haystack), term)


def _month_index(date: str | None) -> int | None:
    """'2023-04' -> an absolute month number. None when unparseable."""
    text = str(date or "").strip()
    match = re.match(r"^(\d{4})-(\d{1,2})", text)
    if match:
        month = min(max(int(match.group(2)), 1), 12)
        return int(match.group(1)) * 12 + month - 1
    match = re.match(r"^(\d{4})$", text)
    if match:
        return int(match.group(1)) * 12
    return None


# Words that carry no topical signal, so an overlap on them means nothing.
_STOPWORDS = {
    "with", "using", "from", "that", "this", "into", "based", "your", "have",
    "been", "were", "will", "over", "more", "than", "also", "such", "each",
    "project", "projects", "system", "application", "applications", "app",
    "development", "developed", "developing", "management", "solution",
    "solutions", "platform", "tool", "tools", "work", "working", "team",
    "level", "national", "multiple", "various", "including", "provide",
    "provided", "used", "make", "made", "build", "built", "building",
    "practice", "problems", "problem", "student", "students", "engineering",
    "technical", "preparation", "actively", "preparing", "performer",
    "among", "under", "solved", "winner", "ranked", "introduction",
}


def _topic_tokens(text: Any) -> set[str]:
    """
    Meaningful words in a title, for overlap scoring.

    Used where a full-title match is too strict: the achievement "Solved 300+
    Data Structures and Algorithms problems" clearly refers to the project
    "Data Structures & Algorithms Practice", but neither string contains the
    other.
    """
    return {
        token for token in _norm(text).split()
        if len(token) >= 4 and token not in _STOPWORDS
    }


# ── Career path archetypes ──────────────────────────────────────────────

_CAREER_PATHS: tuple[dict[str, Any], ...] = (
    {
        "slug": "ai-ml-engineer",
        "title": "AI / Machine Learning Engineer",
        "signals": (
            "machine learning", "deep learning", "artificial intelligence", "nlp",
            "llm", "tensorflow", "pytorch", "keras", "scikit learn", "computer vision",
            "opencv", "generative ai", "neural network", "data science", "langchain",
            "hugging face", "rag", "prompt engineering",
        ),
    },
    {
        "slug": "data-analyst",
        "title": "Data Analyst / Data Engineer",
        "signals": (
            "data analysis", "data analytics", "sql", "pandas", "numpy", "tableau",
            "power bi", "excel", "etl", "data warehouse", "spark", "hadoop",
            "bigquery", "statistics", "data visualization", "dashboard",
        ),
    },
    {
        "slug": "full-stack-developer",
        "title": "Full-Stack Web Developer",
        "signals": (
            "react", "angular", "vue", "next js", "node js", "express js", "django",
            "flask", "fastapi", "html", "css", "tailwind", "javascript", "typescript",
            "rest api", "mongodb", "mysql", "frontend", "backend", "full stack",
            "php", "laravel", "spring boot",
        ),
    },
    {
        "slug": "cloud-devops-engineer",
        "title": "Cloud / DevOps Engineer",
        "signals": (
            "aws", "microsoft azure", "google cloud platform", "docker", "kubernetes",
            "terraform", "ansible", "jenkins", "ci cd", "devops", "linux", "nginx",
            "microservices", "cloud computing", "github actions",
        ),
    },
    {
        "slug": "mobile-developer",
        "title": "Mobile App Developer",
        "signals": (
            "android", "ios", "flutter", "react native", "kotlin", "swift", "dart",
            "jetpack compose", "mobile app", "android studio",
        ),
    },
    {
        "slug": "cybersecurity-engineer",
        "title": "Cybersecurity Engineer",
        "signals": (
            "cybersecurity", "cyber security", "penetration testing", "ethical hacking",
            "network security", "cryptography", "siem", "vulnerability", "owasp",
            "firewall", "kali linux", "information security",
        ),
    },
    {
        "slug": "software-engineer",
        "title": "Software Engineer (Core)",
        "signals": (
            "java", "c++", "c#", "data structures and algorithms", "object oriented",
            "software engineering", "system design", "git", "operating systems",
            "compiler", "spring",
        ),
    },
    {
        "slug": "embedded-iot-engineer",
        "title": "Embedded / IoT Engineer",
        "signals": (
            "arduino", "raspberry pi", "internet of things", "embedded",
            "microcontroller", "esp32", "sensor", "verilog", "vhdl", "robotics",
            "matlab", "pcb",
        ),
    },
)


class RelationshipEngine:
    """
    Discovers explainable relationships across a user's entire entity corpus
    and persists a compact adjacency list into ChromaDB entity metadata.
    """

    # Edges kept per source node, so one very popular skill cannot swamp the map.
    MAX_EDGES_PER_SOURCE = 10
    # Adjacency entries written into a single entity's Chroma metadata.
    MAX_STORED_PER_ENTITY = 8
    # Minimum confidence for an edge to be worth showing.
    MIN_CONFIDENCE = 0.3

    def __init__(self) -> None:
        self.chroma = ChromaClient()

    # ── Corpus loading ──────────────────────────────────────────────────

    def load_user_entities(self, user_id: str = "default") -> list[CategorisedEntity]:
        """
        Read every categorised entity belonging to ``user_id`` out of Chroma.

        This is what makes the graph cross-document: relations are computed over
        the whole corpus rather than the handful of entities from one upload.
        """
        entities: list[CategorisedEntity] = []
        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                result = self.chroma.get_all(
                    col_name, where={"user_id": user_id}, limit=5000
                )
            except Exception as exc:
                logger.warning(f"Could not read collection {col_name}: {exc}")
                continue

            ids = result.get("ids") or []
            docs = result.get("documents") or []
            metas = result.get("metadatas") or []
            for idx, entity_id in enumerate(ids):
                meta = metas[idx] if idx < len(metas) else {}
                doc = docs[idx] if idx < len(docs) else ""
                try:
                    entities.append(document_to_entity(entity_id, doc, meta or {}))
                except Exception as exc:
                    logger.warning(f"Skipping malformed entity {entity_id}: {exc}")
        return entities

    # ── Public API ──────────────────────────────────────────────────────

    def rebuild_user_graph(self, user_id: str = "default") -> KnowledgeGraphResponse:
        """
        Recompute the whole knowledge graph for a user and persist it.

        Called at the end of every ingest. Failures are logged and swallowed:
        the entities are already safely stored by that point, so a graph problem
        must not turn a successful upload into a 500.
        """
        try:
            entities = self.load_user_entities(user_id)
            graph = self.build_graph(user_id, entities)
            self._persist(entities, graph.edges)
            _GRAPH_CACHE[user_id] = graph
            logger.info(
                f"Knowledge graph rebuilt for {user_id}: "
                f"{len(graph.nodes)} nodes, {len(graph.edges)} edges, "
                f"career paths: {', '.join(graph.career_paths) or 'none'}"
            )
            return graph
        except Exception as exc:
            logger.error(f"Graph rebuild failed for {user_id}: {exc}", exc_info=True)
            return KnowledgeGraphResponse(user_id=user_id)

    def get_user_graph(
        self,
        user_id: str = "default",
        refresh: bool = False,
    ) -> KnowledgeGraphResponse:
        """Return the cached graph, rebuilding it on a cache miss or ``refresh``."""
        if refresh:
            return self.rebuild_user_graph(user_id)
        cached = _GRAPH_CACHE.get(user_id)
        if cached is not None:
            return cached
        graph = self.build_graph(user_id)
        _GRAPH_CACHE[user_id] = graph
        return graph

    def get_entity_connections(
        self,
        entity_id: str,
        user_id: str = "default",
    ) -> EntityConnectionsResponse:
        """Every explainable edge touching one entity, strongest first."""
        graph = self.get_user_graph(user_id)
        node = next((n for n in graph.nodes if n.id == entity_id), None)
        connections = [
            edge for edge in graph.edges
            if edge.source_id == entity_id or edge.target_id == entity_id
        ]
        connections.sort(key=lambda e: e.confidence, reverse=True)
        return EntityConnectionsResponse(
            entity_id=entity_id,
            entity_title=node.title if node else "",
            entity_category=node.category if node else "",
            connections=connections,
        )

    # ── Graph construction ──────────────────────────────────────────────

    def build_graph(
        self,
        user_id: str = "default",
        entities: list[CategorisedEntity] | None = None,
    ) -> KnowledgeGraphResponse:
        """Compute nodes + explainable edges. Pure — writes nothing."""
        if entities is None:
            entities = self.load_user_entities(user_id)

        by_cat: dict[EntityCategory, list[CategorisedEntity]] = defaultdict(list)
        for entity in entities:
            by_cat[entity.category].append(entity)

        # Normalised searchable text per entity, computed once — the matchers
        # below are O(entities x terms) and re-normalising dominated the cost.
        text_index = {e.id: _norm(self._entity_text(e)) for e in entities}

        edges: list[EntityRelation] = []
        edges += self._certification_to_skill(
            by_cat[EntityCategory.CERTIFICATION], by_cat[EntityCategory.SKILL], text_index
        )

        # Documents that describe exactly one project. Within such a document,
        # co-occurrence is real evidence: a project report's skills section and
        # its prize are about the one project the report is about. A résumé is
        # about a whole career, so it is excluded — co-occurrence there would
        # attach every skill to whatever project the résumé mentions.
        solo_project_docs = self._single_project_documents(entities)

        # Skill edges come first: the maps they produce are what let a project
        # and an internship be linked through the skills they share, which is
        # the only signal available when a resume gives projects no dates.
        skill_project_edges = self._skill_to_project(
            by_cat[EntityCategory.SKILL],
            by_cat[EntityCategory.PROJECT],
            solo_project_docs,
        )
        internship_skill_edges = self._internship_to_skill(
            by_cat[EntityCategory.INTERNSHIP], by_cat[EntityCategory.SKILL], text_index
        )
        edges += skill_project_edges
        edges += internship_skill_edges

        skills_of_project: dict[str, set[str]] = defaultdict(set)
        for edge in skill_project_edges:
            skills_of_project[edge.target_id].add(edge.source_title)
        skills_of_internship: dict[str, set[str]] = defaultdict(set)
        for edge in internship_skill_edges:
            skills_of_internship[edge.source_id].add(edge.target_title)

        edges += self._project_to_internship(
            by_cat[EntityCategory.PROJECT],
            by_cat[EntityCategory.INTERNSHIP],
            skills_of_project,
            skills_of_internship,
        )
        edges += self._project_to_achievement(
            by_cat[EntityCategory.PROJECT],
            by_cat[EntityCategory.ACHIEVEMENT],
            text_index,
            solo_project_docs,
        )
        edges += self._academics_to_skill(
            by_cat[EntityCategory.ACADEMICS], by_cat[EntityCategory.SKILL], text_index
        )

        career_paths = self._rank_career_paths(entities, text_index)
        career_edges = self._career_edges(career_paths, by_cat, text_index)
        edges += career_edges

        edges = self._dedupe(edges)
        edges = self._cap_per_source(edges)
        edges.sort(key=lambda e: e.confidence, reverse=True)

        # Only keep career nodes that actually got connected — an orphan
        # "career path" bubble in the UI is worse than no bubble.
        connected_ids = {e.source_id for e in edges} | {e.target_id for e in edges}
        nodes = [self._to_node(e) for e in entities]
        nodes += [
            self._career_node(path)
            for path in career_paths
            if f"career::{path['slug']}" in connected_ids
        ]

        degree = Counter()
        for edge in edges:
            degree[edge.source_id] += 1
            degree[edge.target_id] += 1
        for node in nodes:
            node.degree = degree.get(node.id, 0)

        live_paths = [
            path["title"] for path in career_paths
            if f"career::{path['slug']}" in connected_ids
        ]
        return KnowledgeGraphResponse(
            user_id=user_id,
            nodes=nodes,
            edges=edges,
            relation_counts=dict(Counter(e.relation_type for e in edges)),
            career_paths=live_paths,
        )

    # ── Chain: Certification -> Skill ───────────────────────────────────

    def _certification_to_skill(
        self,
        certs: list[CategorisedEntity],
        skills: list[CategorisedEntity],
        text_index: dict[str, str],
    ) -> list[EntityRelation]:
        """A certification certifies a skill when it names that skill."""
        edges: list[EntityRelation] = []
        for cert in certs:
            haystack = text_index.get(cert.id) or _norm(self._entity_text(cert))
            issuer = (cert.data or {}).get("issuer") or ""
            for skill in skills:
                matched = _find_in_norm(haystack, skill.title)
                if not matched:
                    continue

                evidence = [RelationEvidence(
                    kind="name_match",
                    detail=f'"{cert.title}" names "{matched}"',
                    weight=0.55,
                )]
                if _norm(cert.title) == _norm(skill.title):
                    evidence.append(RelationEvidence(
                        kind="name_match",
                        detail="Certification is dedicated to exactly this skill",
                        weight=0.2,
                    ))
                if issuer:
                    evidence.append(RelationEvidence(
                        kind="shared_tag",
                        detail=f"Issued by {issuer}",
                        weight=0.05,
                    ))
                if cert.importance_score >= 8:
                    evidence.append(RelationEvidence(
                        kind="semantic",
                        detail=f"High-value certification (score {cert.importance_score}/10)",
                        weight=0.1,
                    ))

                edges.append(self._edge(
                    cert, skill, "certifies",
                    f'"{cert.title}" formally certifies your {skill.title} skill.',
                    evidence,
                ))
        return edges

    # ── Chain: Skill -> Project ─────────────────────────────────────────

    def _skill_to_project(
        self,
        skills: list[CategorisedEntity],
        projects: list[CategorisedEntity],
        solo_project_docs: dict[str, str] | None = None,
    ) -> list[EntityRelation]:
        """A skill is used_in a project via its tech stack or description."""
        edges: list[EntityRelation] = []
        solo_project_docs = solo_project_docs or {}
        for project in projects:
            stack = [str(t) for t in (project.data or {}).get("tech_stack", []) if t]
            stack += [t for t in (project.tags or []) if t]
            # Exact stack membership is checked on the normalised form, which
            # lets even one-character entries ("C", "R") match safely — unlike
            # free-text search, a list item is an unambiguous declaration.
            stack_norm = {_norm(t) for t in stack}
            stack_norm.discard("")
            prose = _norm(
                f"{project.title} {(project.data or {}).get('description') or ''}"
            )

            for skill in skills:
                evidence: list[RelationEvidence] = []
                spellings = set(_variants(skill.title)) | {_norm(skill.title)}

                hit = next((s for s in spellings if s in stack_norm), None)
                if hit:
                    evidence.append(RelationEvidence(
                        kind="tech_match",
                        detail=f'"{hit}" is listed in this project\'s tech stack',
                        weight=0.6,
                    ))
                else:
                    matched = _find_in_norm(prose, skill.title)
                    if matched:
                        evidence.append(RelationEvidence(
                            kind="mentioned_in",
                            detail=f'Project description mentions "{matched}"',
                            weight=0.4,
                        ))
                    elif solo_project_docs.get(skill.file_id or "") == project.id:
                        # A project report lists the skills it demonstrated in
                        # its own prose, phrased differently from the tech stack
                        # ("LSTM model design" vs "PyTorch"). Without this the
                        # skills a report introduces stay orphaned on the map
                        # while the project it introduced them for is connected.
                        evidence.append(RelationEvidence(
                            kind="mentioned_in",
                            detail=(
                                "Extracted from the same document, which "
                                "describes only this project"
                            ),
                            weight=0.35,
                        ))

                if not evidence:
                    continue

                shared_tags = {_norm(t) for t in skill.tags} & {_norm(t) for t in project.tags}
                shared_tags.discard("")
                if shared_tags:
                    evidence.append(RelationEvidence(
                        kind="shared_tag",
                        detail=f"Shared tag: {', '.join(sorted(shared_tags)[:3])}",
                        weight=0.1,
                    ))
                if skill.importance_score >= 8:
                    evidence.append(RelationEvidence(
                        kind="semantic",
                        detail=f"Advanced-level skill (score {skill.importance_score}/10)",
                        weight=0.1,
                    ))
                if project.date:
                    evidence.append(RelationEvidence(
                        kind="temporal",
                        detail=f"Applied around {project.date}",
                        weight=0.05,
                    ))

                edges.append(self._edge(
                    skill, project, "used_in",
                    f'You applied {skill.title} while building "{project.title}".',
                    evidence,
                ))
        return edges

    # ── Chain: Internship -> Skill ──────────────────────────────────────

    def _internship_to_skill(
        self,
        internships: list[CategorisedEntity],
        skills: list[CategorisedEntity],
        text_index: dict[str, str],
    ) -> list[EntityRelation]:
        """An internship developed a skill when its work description names it."""
        edges: list[EntityRelation] = []
        for internship in internships:
            data = internship.data or {}
            description = _norm(data.get("description") or "")
            role = _norm(data.get("role") or "")
            haystack = text_index.get(internship.id) or _norm(self._entity_text(internship))

            for skill in skills:
                matched = _find_in_norm(haystack, skill.title)
                if not matched:
                    continue

                evidence: list[RelationEvidence] = []
                if _find_in_norm(description, skill.title):
                    evidence.append(RelationEvidence(
                        kind="mentioned_in",
                        detail=f'Internship work description mentions "{matched}"',
                        weight=0.45,
                    ))
                if _find_in_norm(role, skill.title):
                    evidence.append(RelationEvidence(
                        kind="name_match",
                        detail=f'The role itself is "{matched}"-focused',
                        weight=0.2,
                    ))
                if not evidence:
                    evidence.append(RelationEvidence(
                        kind="mentioned_in",
                        detail=f'This internship record mentions "{matched}"',
                        weight=0.35,
                    ))
                if internship.date:
                    evidence.append(RelationEvidence(
                        kind="temporal",
                        detail=f"Practised from {internship.date}",
                        weight=0.05,
                    ))

                edges.append(self._edge(
                    internship, skill, "developed",
                    f"Your {internship.title} role developed {skill.title}.",
                    evidence,
                ))
        return edges

    # ── Chain: Project -> Internship ────────────────────────────────────

    def _project_to_internship(
        self,
        projects: list[CategorisedEntity],
        internships: list[CategorisedEntity],
        skills_of_project: dict[str, set[str]],
        skills_of_internship: dict[str, set[str]],
    ) -> list[EntityRelation]:
        """
        Connect a project to the internship it belongs with.

        Four independent signals, strongest first: the company is named in the
        project, the project's date falls inside the internship window, the two
        share technologies, or they share skills. Resumes very often give
        projects no dates at all, so the skill/tech bridges are what keep this
        chain alive rather than empty.
        """
        edges: list[EntityRelation] = []
        for internship in internships:
            data = internship.data or {}
            company = str(data.get("company") or "").strip()
            role = str(data.get("role") or "Intern").strip()
            intern_text = _norm(f"{data.get('description') or ''} {role} {company}")
            start = _month_index(internship.date) or _month_index(data.get("start_date"))
            end = _month_index(data.get("end_date"))
            intern_skills = {s.lower() for s in skills_of_internship.get(internship.id, ())}

            for project in projects:
                evidence: list[RelationEvidence] = []
                proj_text = _norm(
                    f"{project.title} {(project.data or {}).get('description') or ''}"
                )

                company_named = bool(company and _find_in_norm(proj_text, company))
                if company_named:
                    evidence.append(RelationEvidence(
                        kind="mentioned_in",
                        detail=f'Project text names "{company}"',
                        weight=0.5,
                    ))

                # Date containment is the strongest temporal signal; nearby
                # dates are weaker but still worth surfacing. When both dates
                # are known but sit more than six months apart, the project was
                # demonstrably *not* built during this internship — record that
                # contradiction so the edge below isn't phrased as an overlap.
                proj_month = _month_index(project.date)
                temporal_contradiction = False
                if proj_month is not None and start is not None:
                    window_end = end if end is not None else start + 6
                    if start <= proj_month <= window_end:
                        evidence.append(RelationEvidence(
                            kind="temporal",
                            detail=(
                                f"Built {project.date}, inside the "
                                f"{internship.date or data.get('start_date')}"
                                f"–{data.get('end_date') or 'present'} window"
                            ),
                            weight=0.45,
                        ))
                    elif abs(proj_month - start) <= 6:
                        evidence.append(RelationEvidence(
                            kind="temporal",
                            detail=(
                                f"Built {project.date}, within "
                                f"{abs(proj_month - start)} month(s) of this internship"
                            ),
                            weight=0.2,
                        ))
                    else:
                        temporal_contradiction = True

                shared_tech = []
                for tech in (project.data or {}).get("tech_stack", [])[:12]:
                    if tech and _find_in_norm(intern_text, str(tech)):
                        shared_tech.append(str(tech))
                if shared_tech:
                    evidence.append(RelationEvidence(
                        kind="tech_match",
                        detail=f"Shared technology: {', '.join(shared_tech[:3])}",
                        weight=min(0.2 + 0.1 * len(shared_tech), 0.45),
                    ))

                # Skill bridge: both records independently connect to the same
                # skills, which is real shared substance even with no dates.
                shared_skills = sorted(
                    {s.lower() for s in skills_of_project.get(project.id, ())} & intern_skills
                )
                extra = [s for s in shared_skills if s not in {t.lower() for t in shared_tech}]
                if extra:
                    evidence.append(RelationEvidence(
                        kind="shared_tag",
                        detail=f"Both involve {', '.join(extra[:3])}",
                        weight=min(0.18 + 0.09 * len(extra), 0.4),
                    ))

                if not evidence:
                    continue

                # `built_during` asserts the project happened within the
                # internship. If the dates are known and place it clearly
                # outside the window, a shared language or skill is not enough
                # to claim that — only a direct company mention keeps the edge,
                # and even then it is phrased as association, not overlap.
                if temporal_contradiction and not company_named:
                    continue

                where = f"{role} role at {company}" if company else internship.title
                if temporal_contradiction:
                    label = f'"{project.title}" was done for your {where}, though built at a different time.'
                else:
                    label = f'"{project.title}" lines up with your {where}.'
                edges.append(self._edge(
                    project, internship, "built_during", label, evidence,
                ))
        return edges

    # ── Chain: Project -> Achievement ───────────────────────────────────

    def _project_to_achievement(
        self,
        projects: list[CategorisedEntity],
        achievements: list[CategorisedEntity],
        text_index: dict[str, str],
        solo_project_docs: dict[str, str] | None = None,
    ) -> list[EntityRelation]:
        """
        An achievement recognises a project when it names it, when the two
        share enough topical words to be talking about the same thing, or when
        both come out of a document about that one project.
        """
        edges: list[EntityRelation] = []
        solo_project_docs = solo_project_docs or {}
        for achievement in achievements:
            ach_text = text_index.get(achievement.id) or _norm(self._entity_text(achievement))
            ach_tokens = _topic_tokens(self._entity_text(achievement))
            ach_month = _month_index(achievement.date)

            for project in projects:
                evidence: list[RelationEvidence] = []
                if len(_norm(project.title)) >= 4 and _find_in_norm(ach_text, project.title):
                    evidence.append(RelationEvidence(
                        kind="name_match",
                        detail=f'"{achievement.title}" names this project',
                        weight=0.6,
                    ))
                else:
                    # Two shared topical words is the floor — one is usually
                    # coincidence ("data" appears everywhere).
                    shared = sorted(_topic_tokens(project.title) & ach_tokens)
                    if len(shared) >= 2:
                        evidence.append(RelationEvidence(
                            kind="name_match",
                            detail=f"Both are about {', '.join(shared[:3])}",
                            weight=min(0.3 + 0.12 * (len(shared) - 2), 0.55),
                        ))
                    elif solo_project_docs.get(achievement.file_id or "") == project.id:
                        # A prize named for a hackathon rather than for the entry
                        # ("First Prize, Smart India Hackathon") shares no words
                        # with the project title, so neither test above fires —
                        # but the report's recognition section is unambiguously
                        # about the one project the report describes.
                        evidence.append(RelationEvidence(
                            kind="mentioned_in",
                            detail=(
                                "Recorded in the same document, which describes "
                                "only this project"
                            ),
                            weight=0.45,
                        ))

                proj_month = _month_index(project.date)
                if evidence and ach_month is not None and proj_month is not None:
                    gap = abs(ach_month - proj_month)
                    if gap <= 12:
                        evidence.append(RelationEvidence(
                            kind="temporal",
                            detail=f"Awarded within {gap} month(s) of the project",
                            weight=0.15,
                        ))

                if not evidence:
                    continue
                edges.append(self._edge(
                    project, achievement, "recognised_by",
                    f'"{project.title}" is recognised by "{achievement.title}".',
                    evidence,
                ))
        return edges

    # ── Chain: Academics -> Skill ───────────────────────────────────────

    def _academics_to_skill(
        self,
        academics: list[CategorisedEntity],
        skills: list[CategorisedEntity],
        text_index: dict[str, str],
    ) -> list[EntityRelation]:
        """A degree taught a skill when the programme text names it."""
        edges: list[EntityRelation] = []
        for record in academics:
            haystack = text_index.get(record.id) or _norm(self._entity_text(record))
            for skill in skills:
                matched = _find_in_norm(haystack, skill.title)
                if not matched:
                    continue
                evidence = [RelationEvidence(
                    kind="mentioned_in",
                    detail=f'"{record.title}" mentions "{matched}"',
                    weight=0.45,
                )]
                if record.date:
                    evidence.append(RelationEvidence(
                        kind="temporal",
                        detail=f"Studied around {record.date}",
                        weight=0.05,
                    ))
                edges.append(self._edge(
                    record, skill, "taught",
                    f"Your studies at {record.title} covered {skill.title}.",
                    evidence,
                ))
        return edges

    # ── Chain: Internship -> Career Path ────────────────────────────────

    def _rank_career_paths(
        self,
        entities: list[CategorisedEntity],
        text_index: dict[str, str],
    ) -> list[dict[str, Any]]:
        """
        Score career archetypes against the whole corpus.

        A path qualifies on at least two distinct signals, so one stray keyword
        cannot invent a career direction. The top path always qualifies; a
        runner-up is kept when it reaches 60% of the leader's score.
        """
        scored: list[dict[str, Any]] = []
        for path in _CAREER_PATHS:
            matched: dict[str, list[str]] = {}
            for entity in entities:
                haystack = text_index.get(entity.id, "")
                if not haystack:
                    continue
                for signal in path["signals"]:
                    if _find_in_norm(haystack, signal):
                        supporters = matched.setdefault(signal, [])
                        if len(supporters) < 5:
                            supporters.append(entity.title)
            if len(matched) < 2:
                continue
            support = sum(len(v) for v in matched.values())
            scored.append({
                **path,
                "matched": matched,
                # Breadth of distinct signals matters more than raw repetition.
                "score": len(matched) * 2 + support * 0.25,
            })

        scored.sort(key=lambda p: p["score"], reverse=True)
        if not scored:
            return []
        top = scored[0]
        return [top] + [p for p in scored[1:3] if p["score"] >= top["score"] * 0.6]

    def _career_edges(
        self,
        career_paths: list[dict[str, Any]],
        by_cat: dict[EntityCategory, list[CategorisedEntity]],
        text_index: dict[str, str],
    ) -> list[EntityRelation]:
        """
        Link real experience to each derived career path.

        Internships are the intended source. When a user has none (or none that
        match), the strongest projects stand in — otherwise the career node
        would float unconnected and the chain would be invisible in the demo.
        """
        if not career_paths:
            return []

        edges: list[EntityRelation] = []
        internships = by_cat.get(EntityCategory.INTERNSHIP, [])
        for path in career_paths:
            node = self._career_node(path)
            linked = 0
            for internship in internships:
                edge = self._career_edge(internship, path, node, text_index, "internship")
                if edge:
                    edges.append(edge)
                    linked += 1
            if linked:
                continue

            fallback = sorted(
                by_cat.get(EntityCategory.PROJECT, []),
                key=lambda p: p.importance_score,
                reverse=True,
            )[:3]
            for project in fallback:
                edge = self._career_edge(project, path, node, text_index, "project")
                if edge:
                    edges.append(edge)
        return edges

    def _career_edge(
        self,
        source: CategorisedEntity,
        path: dict[str, Any],
        node: GraphNode,
        text_index: dict[str, str],
        source_kind: str,
    ) -> EntityRelation | None:
        haystack = text_index.get(source.id, "")
        hits = [s for s in path["signals"] if _find_in_norm(haystack, s)]
        if not hits:
            return None

        evidence = [RelationEvidence(
            kind="career_signal",
            detail=f"This {source_kind} involves {', '.join(hits[:4])}",
            weight=min(0.35 + 0.1 * len(hits), 0.65),
        )]
        corpus_signals = sorted(path["matched"], key=lambda s: -len(path["matched"][s]))[:4]
        evidence.append(RelationEvidence(
            kind="career_signal",
            detail=(
                f"{len(path['matched'])} signals across your profile point the same "
                f"way ({', '.join(corpus_signals)})"
            ),
            weight=0.2,
        ))
        if source.importance_score >= 8:
            evidence.append(RelationEvidence(
                kind="semantic",
                detail=f"High-impact record (score {source.importance_score}/10)",
                weight=0.1,
            ))

        return self._edge(
            source, node, "leads_to",
            f'"{source.title}" points toward a {path["title"]} track.',
            evidence,
        )

    # ── Edge plumbing ───────────────────────────────────────────────────

    @staticmethod
    def _edge(
        source: CategorisedEntity | GraphNode,
        target: CategorisedEntity | GraphNode,
        relation_type: str,
        label: str,
        evidence: list[RelationEvidence],
    ) -> EntityRelation:
        """Assemble an edge, deriving confidence from the summed evidence weight."""
        confidence = min(round(sum(ev.weight for ev in evidence), 3), 1.0)
        return EntityRelation(
            source_id=source.id,
            source_title=source.title,
            source_category=RelationshipEngine._category_of(source),
            target_id=target.id,
            target_title=target.title,
            target_category=RelationshipEngine._category_of(target),
            relation_type=relation_type,
            label=label,
            confidence=max(confidence, 0.0),
            evidence=evidence,
        )

    @staticmethod
    def _category_of(item: CategorisedEntity | GraphNode) -> str:
        category = getattr(item, "category", "")
        return getattr(category, "value", category) or ""

    def _dedupe(self, edges: list[EntityRelation]) -> list[EntityRelation]:
        """Collapse repeated (source, target, type) triples, keeping all evidence."""
        merged: dict[tuple[str, str, str], EntityRelation] = {}
        for edge in edges:
            if edge.confidence < self.MIN_CONFIDENCE:
                continue
            key = (edge.source_id, edge.target_id, edge.relation_type)
            existing = merged.get(key)
            if existing is None:
                merged[key] = edge
                continue
            seen = {(ev.kind, ev.detail) for ev in existing.evidence}
            existing.evidence.extend(
                ev for ev in edge.evidence if (ev.kind, ev.detail) not in seen
            )
            existing.confidence = max(existing.confidence, edge.confidence)
        return list(merged.values())

    def _cap_per_source(self, edges: list[EntityRelation]) -> list[EntityRelation]:
        """Keep only the strongest edges per source node to bound graph density."""
        grouped: dict[str, list[EntityRelation]] = defaultdict(list)
        for edge in edges:
            grouped[edge.source_id].append(edge)

        kept: list[EntityRelation] = []
        dropped = 0
        for source_edges in grouped.values():
            source_edges.sort(key=lambda e: e.confidence, reverse=True)
            kept.extend(source_edges[: self.MAX_EDGES_PER_SOURCE])
            dropped += max(0, len(source_edges) - self.MAX_EDGES_PER_SOURCE)
        if dropped:
            logger.info(
                f"Graph density capped: kept top {self.MAX_EDGES_PER_SOURCE} "
                f"edge(s) per node, {dropped} weaker edge(s) not shown"
            )
        return kept

    # Categories that mark a document as a career summary rather than a document
    # about one thing. A résumé carries a degree, a certificate or a job; a
    # project report does not.
    _CAREER_SUMMARY_MARKERS = frozenset({
        EntityCategory.INTERNSHIP,
        EntityCategory.CERTIFICATION,
        EntityCategory.ACADEMICS,
    })

    @classmethod
    def _single_project_documents(
        cls,
        entities: list[CategorisedEntity],
    ) -> dict[str, str]:
        """
        Map ``file_id -> project_id`` for documents that are *about* one project.

        This is the guard that makes same-document co-occurrence usable as
        evidence. A project report is about one thing, so anything else
        extracted from it — the skills it demonstrated, the prize it won — is
        about that thing too.

        Two tests, both required:

        1. The document produced exactly one project.
        2. It produced no internship, certification or academics entity.

        Test 1 alone is not enough, and skipping test 2 was a real bug: a résumé
        that happened to describe only one project passed test 1, and its 27
        career-wide skills — data structures, an IDE, an unrelated database —
        were all attached to that one project. Test 2 rejects it, because a
        document that records someone's degree and internship is a summary of a
        career, not a report on a project.

        The failure direction is deliberate: a report whose course line gets read
        as an academic record loses its co-occurrence edges and leaves a few
        skills unconnected. That is a much better outcome than confidently
        drawing edges that are wrong.
        """
        by_document: dict[str, list[str]] = defaultdict(list)
        disqualified: set[str] = set()
        for entity in entities:
            if not entity.file_id:
                continue  # pre-file_id ingests get no co-occurrence evidence
            if entity.category is EntityCategory.PROJECT:
                by_document[entity.file_id].append(entity.id)
            elif entity.category in cls._CAREER_SUMMARY_MARKERS:
                disqualified.add(entity.file_id)

        return {
            file_id: ids[0]
            for file_id, ids in by_document.items()
            if len(ids) == 1 and file_id not in disqualified
        }

    @staticmethod
    def _to_node(entity: CategorisedEntity) -> GraphNode:
        return GraphNode(
            id=entity.id,
            title=entity.title,
            category=entity.category.value,
            date=entity.date,
            importance_score=entity.importance_score,
            tags=entity.tags[:8],
            file_id=entity.file_id,
        )

    @staticmethod
    def _career_node(path: dict[str, Any]) -> GraphNode:
        return GraphNode(
            id=f"career::{path['slug']}",
            title=path["title"],
            category=CAREER_PATH_CATEGORY,
            importance_score=9,
            tags=sorted(path.get("matched", {}))[:8],
        )

    @staticmethod
    def _entity_text(entity: CategorisedEntity) -> str:
        """All searchable text for an entity: title, tags and every data value."""
        parts: list[str] = [entity.title, *(entity.tags or [])]
        for value in (entity.data or {}).values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value if v)
            elif isinstance(value, dict):
                parts.extend(str(v) for v in value.values() if v)
        return " ".join(p for p in parts if p)

    # ── Persistence ─────────────────────────────────────────────────────

    def _persist(
        self,
        entities: list[CategorisedEntity],
        edges: list[EntityRelation],
    ) -> None:
        """
        Write a compact adjacency list into each entity's Chroma metadata.

        The stored form carries ``target_title``, ``label`` and ``why`` so that
        consumers (the timeline, the entity detail panel) can render a readable
        connection without a second round of lookups.

        Entities with no edges are written too — with an empty list — so that a
        relation removed by this rebuild does not linger in stale metadata.
        """
        adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            why = "; ".join(ev.detail for ev in edge.evidence[:3])
            adjacency[edge.source_id].append({
                "target_id": edge.target_id,
                "target_title": edge.target_title,
                "target_category": edge.target_category,
                "type": edge.relation_type,
                "direction": "out",
                "label": edge.label,
                "confidence": round(edge.confidence, 2),
                "why": why,
            })
            adjacency[edge.target_id].append({
                "target_id": edge.source_id,
                "target_title": edge.source_title,
                "target_category": edge.source_category,
                "type": edge.relation_type,
                "direction": "in",
                "label": edge.label,
                "confidence": round(edge.confidence, 2),
                "why": why,
            })

        for entries in adjacency.values():
            entries.sort(key=lambda r: r["confidence"], reverse=True)

        by_collection: dict[str, list[str]] = defaultdict(list)
        for entity in entities:
            by_collection[collection_for_category(entity.category)].append(entity.id)

        for col_name, ids in by_collection.items():
            try:
                col = self.chroma.get_collection(col_name)
            except Exception as exc:
                logger.warning(f"Cannot open {col_name} to store relations: {exc}")
                continue

            for batch in _chunks(ids, 200):
                try:
                    existing = col.get(ids=batch, include=["metadatas"])
                except Exception as exc:
                    logger.warning(f"Relation write skipped for {col_name}: {exc}")
                    continue

                found_ids = existing.get("ids") or []
                found_metas = existing.get("metadatas") or []
                if not found_ids:
                    continue

                metadatas = []
                for idx, entity_id in enumerate(found_ids):
                    meta = dict(found_metas[idx] or {}) if idx < len(found_metas) else {}
                    entries = adjacency.get(entity_id, [])
                    meta["relations"] = json.dumps(entries[: self.MAX_STORED_PER_ENTITY])
                    meta["relation_count"] = len(entries)
                    metadatas.append(meta)

                try:
                    col.update(ids=found_ids, metadatas=metadatas)
                except Exception as exc:
                    logger.warning(f"Relation update failed for {col_name}: {exc}")

    # ── Legacy API (kept for scripts/seed_demo.py and older callers) ────

    def build_relations(
        self,
        entities: list[CategorisedEntity],
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        """
        Legacy shim: relations for a fixed entity list as plain dicts.

        Prefer :meth:`rebuild_user_graph`, which reads the user's whole corpus
        instead of a single document's entities.
        """
        graph = self.build_graph(user_id, entities)
        return [
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "relation_type": edge.relation_type,
                # Historic callers expect a 1-10 relevance score.
                "relevance_score": max(1, round(edge.confidence * 10)),
                "label": edge.label,
                "why": [ev.detail for ev in edge.evidence],
            }
            for edge in graph.edges
        ]

    def store_relations(
        self,
        entities: list[CategorisedEntity],
        relations: list[dict[str, Any]],
    ) -> None:
        """Legacy shim: persist relation dicts produced by :meth:`build_relations`."""
        by_id = {e.id: e for e in entities}
        edges: list[EntityRelation] = []
        for rel in relations:
            source = by_id.get(rel.get("source_id", ""))
            target = by_id.get(rel.get("target_id", ""))
            if not source or not target:
                continue
            edges.append(self._edge(
                source, target,
                rel.get("relation_type", "related_to"),
                rel.get("label") or f'"{source.title}" relates to "{target.title}".',
                [RelationEvidence(
                    kind="semantic",
                    detail=detail,
                    weight=0.0,
                ) for detail in (rel.get("why") or [])],
            ))
            edges[-1].confidence = min(float(rel.get("relevance_score", 5)) / 10, 1.0)
        self._persist(entities, edges)

    def get_related_entities(self, entity_id: str) -> list[dict[str, Any]]:
        """
        Read an entity's stored adjacency list out of Chroma metadata.

        Each entry carries ``target_title``, ``label``, ``confidence`` and
        ``why`` alongside ``target_id``.
        """
        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                col = self.chroma.get_collection(col_name)
                result = col.get(ids=[entity_id], include=["metadatas"])
                if result and result.get("ids"):
                    meta = (result.get("metadatas") or [{}])[0] or {}
                    raw = meta.get("relations", "[]")
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                    return parsed if isinstance(parsed, list) else []
            except Exception:
                continue
        return []


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]
