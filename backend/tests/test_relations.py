"""
Tests for the relationship engine (Module 3).

``build_graph`` is pure when handed an entity list, so these run without Chroma
or an embedding model: ``__init__`` only constructs a ChromaClient, which
nothing in this file needs, so it is bypassed.
"""

import pytest
from app.core.vectordb.relations import RelationshipEngine
from app.models.schemas import CategorisedEntity, EntityCategory


def _engine() -> RelationshipEngine:
    return object.__new__(RelationshipEngine)


def _entity(category, title, *, file_id=None, score=5, date=None, tags=(), **data):
    return CategorisedEntity(
        category=category,
        title=title,
        data=dict(data),
        importance_score=score,
        tags=list(tags),
        date=date,
        file_id=file_id,
    )


def _edge(graph, source_title, target_title):
    return next(
        (e for e in graph.edges
         if e.source_title == source_title and e.target_title == target_title),
        None,
    )


class TestSingleProjectDocuments:
    def test_a_document_with_one_project_is_indexed(self):
        report = _entity(EntityCategory.PROJECT, "RiverGuard", file_id="f-report")
        skill = _entity(EntityCategory.SKILL, "LSTM design", file_id="f-report")
        assert RelationshipEngine._single_project_documents([report, skill]) == {
            "f-report": report.id
        }

    def test_a_resume_with_several_projects_is_excluded(self):
        # Co-occurrence inside a resume would link every skill to every project.
        projects = [
            _entity(EntityCategory.PROJECT, "Chatbot", file_id="f-cv"),
            _entity(EntityCategory.PROJECT, "Sentiment Pipeline", file_id="f-cv"),
        ]
        assert RelationshipEngine._single_project_documents(projects) == {}

    @pytest.mark.parametrize("marker", [
        EntityCategory.INTERNSHIP,
        EntityCategory.CERTIFICATION,
        EntityCategory.ACADEMICS,
    ])
    def test_a_resume_naming_one_project_is_still_excluded(self, marker):
        # The bug this guards: a résumé describing a single project passed the
        # one-project test, and its whole career's worth of skills — data
        # structures, an IDE, an unrelated database — attached to that project.
        # A document holding a degree, a certificate or a job is a career
        # summary, whatever its project count.
        entities = [
            _entity(EntityCategory.PROJECT, "Traveo", file_id="f-cv"),
            _entity(marker, "B.E. Computer Engineering", file_id="f-cv"),
        ]
        assert RelationshipEngine._single_project_documents(entities) == {}

    def test_entities_without_a_file_id_are_skipped(self):
        # Pre-file_id ingests get no co-occurrence evidence rather than a wrong one.
        assert RelationshipEngine._single_project_documents(
            [_entity(EntityCategory.PROJECT, "Old Project")]
        ) == {}


class TestCoOccurrenceEvidence:
    """
    A project report names its skills in prose ("LSTM model design") and its
    prize after the organiser ("First Prize, Smart India Hackathon"), so neither
    matches the tech stack or the project title. Before this rule those entities
    stayed orphaned on the knowledge map while the project itself was connected.
    """

    @pytest.fixture
    def report_entities(self):
        return [
            _entity(
                EntityCategory.PROJECT, "RiverGuard Flood Early-Warning System",
                file_id="f-report", date="2025-03", score=9,
                tech_stack=["Python", "FastAPI", "PyTorch"],
                description="Flood early-warning platform for small river basins.",
            ),
            _entity(EntityCategory.SKILL, "LSTM model design",
                    file_id="f-report", date="2025-03", score=8),
            _entity(EntityCategory.SKILL, "PyTorch", file_id="f-report", score=8),
            _entity(EntityCategory.ACHIEVEMENT,
                    "First Prize at Smart India Hackathon 2025 regional round",
                    file_id="f-report", date="2025-03", score=9),
        ]

    def test_skill_named_only_in_prose_is_connected(self, report_entities):
        graph = _engine().build_graph("u", report_entities)
        edge = _edge(graph, "LSTM model design",
                     "RiverGuard Flood Early-Warning System")
        assert edge is not None
        assert edge.relation_type == "used_in"
        assert "describes only this project" in edge.evidence[0].detail

    def test_a_declared_tech_stack_match_still_outranks_co_occurrence(
        self, report_entities
    ):
        graph = _engine().build_graph("u", report_entities)
        declared = _edge(graph, "PyTorch", "RiverGuard Flood Early-Warning System")
        inferred = _edge(graph, "LSTM model design",
                         "RiverGuard Flood Early-Warning System")
        # An explicit tech-stack listing is stronger evidence than co-location,
        # and the confidence ordering has to say so.
        assert declared.confidence > inferred.confidence
        assert declared.evidence[0].kind == "tech_match"

    def test_the_prize_is_connected_to_the_project_it_was_won_for(
        self, report_entities
    ):
        graph = _engine().build_graph("u", report_entities)
        edge = _edge(graph, "RiverGuard Flood Early-Warning System",
                     "First Prize at Smart India Hackathon 2025 regional round")
        assert edge is not None
        assert edge.relation_type == "recognised_by"
        assert edge.confidence >= RelationshipEngine.MIN_CONFIDENCE

    def test_nothing_in_the_report_is_left_orphaned(self, report_entities):
        graph = _engine().build_graph("u", report_entities)
        connected = {e.source_id for e in graph.edges} | {
            e.target_id for e in graph.edges
        }
        assert [e.title for e in report_entities if e.id not in connected] == []

    def test_a_resume_does_not_get_co_occurrence_edges(self):
        # Same shapes, but a career summary: one project, an unrelated skill, and
        # a degree. The skill matches neither tech stack nor prose, so it must
        # stay unconnected rather than be attached to the résumé's one project.
        entities = [
            _entity(EntityCategory.PROJECT, "Traveo", file_id="f-cv",
                    tech_stack=["Python"]),
            _entity(EntityCategory.ACADEMICS, "B.E. Computer Engineering",
                    file_id="f-cv"),
            _entity(EntityCategory.SKILL, "Binary Search", file_id="f-cv"),
        ]
        graph = _engine().build_graph("u", entities)
        assert _edge(graph, "Binary Search", "Traveo") is None

    def test_a_certificate_does_not_recognise_a_resume_project(self):
        # "Programming in Java NPTEL" shares no words with the project and did
        # not name it; co-locating in a résumé is not recognition.
        entities = [
            _entity(EntityCategory.PROJECT, "Traveo", file_id="f-cv", date="2025-01"),
            _entity(EntityCategory.CERTIFICATION, "Programming in Java NPTEL",
                    file_id="f-cv", date="2025-01"),
            _entity(EntityCategory.ACHIEVEMENT, "Career & Technical Preparation",
                    file_id="f-cv", date="2025-01"),
        ]
        graph = _engine().build_graph("u", entities)
        assert _edge(graph, "Traveo", "Career & Technical Preparation") is None


class TestBuiltDuringDates:
    """
    `built_during` asserts a project happened *within* an internship. When both
    dates are known and sit more than six months apart, a shared language alone
    must not manufacture that claim.
    """

    def test_shared_tech_but_contradicting_dates_makes_no_edge(self):
        internship = _entity(
            EntityCategory.INTERNSHIP, "ML Intern", file_id="f-a",
            date="2023-01", company="Acme", role="ML Intern", end_date="2023-06",
            description="Built data pipelines in Python.",
        )
        # Same language, but two years later and no company mention.
        project = _entity(
            EntityCategory.PROJECT, "Weekend Scraper", file_id="f-b",
            date="2025-09", tech_stack=["Python"],
            description="A personal side project.",
        )
        graph = _engine().build_graph("u", [internship, project])
        assert _edge(graph, "Weekend Scraper", "ML Intern") is None

    def test_company_named_survives_but_is_not_called_an_overlap(self):
        internship = _entity(
            EntityCategory.INTERNSHIP, "ML Intern", file_id="f-a",
            date="2023-01", company="Acme", role="ML Intern", end_date="2023-06",
            description="Built data pipelines in Python.",
        )
        project = _entity(
            EntityCategory.PROJECT, "Acme Dashboard", file_id="f-b",
            date="2025-09", tech_stack=["Python"],
            description="An internal dashboard built for Acme.",
        )
        graph = _engine().build_graph("u", [internship, project])
        edge = _edge(graph, "Acme Dashboard", "ML Intern")
        assert edge is not None
        assert edge.relation_type == "built_during"
        # Honest wording: it is associated with the employer, not built during.
        assert "different time" in edge.label
        assert "lines up with" not in edge.label

    def test_overlapping_dates_still_read_as_lining_up(self):
        internship = _entity(
            EntityCategory.INTERNSHIP, "ML Intern", file_id="f-a",
            date="2025-01", company="Acme", role="ML Intern", end_date="2025-12",
            description="Built data pipelines in Python.",
        )
        project = _entity(
            EntityCategory.PROJECT, "Realtime Metrics", file_id="f-b",
            date="2025-06", tech_stack=["Python"],
            description="A metrics service.",
        )
        graph = _engine().build_graph("u", [internship, project])
        edge = _edge(graph, "Realtime Metrics", "ML Intern")
        assert edge is not None
        assert "lines up with" in edge.label
        assert "different time" not in edge.label
