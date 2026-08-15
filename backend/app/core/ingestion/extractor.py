"""
LLM Structured Extraction — uses LangChain + Groq to extract typed entities
from raw document text via structured JSON output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.models.schemas import (
    Achievement,
    Certification,
    ExtractionResult,
    Internship,
    Project,
    Skill,
    Academic,
)
from app.utils.logger import logger

# ── Extraction Prompt ───────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a structured-data extraction engine. Given a document's text, extract
ALL of the following entities you can find. Return valid JSON matching the schema
exactly. If a field is not present, use null. Do NOT invent information.

Return JSON with these top-level keys:
{{
  "certifications": [ {{ "name": str, "issuer": str|null, "date": str|null, "credential_id": str|null }} ],
  "skills":         [ {{ "name": str, "level": str|null, "category": str|null }} ],
  "projects":       [ {{ "name": str, "description": str|null, "tech_stack": [str], "date_range": str|null, "url": str|null }} ],
  "internships":    [ {{ "company": str, "role": str|null, "start_date": str|null, "end_date": str|null, "description": str|null }} ],
  "achievements":   [ {{ "title": str, "description": str|null, "date": str|null, "impact": str|null }} ],
  "academics":      [ {{ "institution": str, "degree": str|null, "start_date": str|null, "end_date": str|null, "description": str|null }} ]
}}

Rules:
- Extract dates in any format you find (e.g. "Jan 2023", "2023-01", "2023").
- For skills, infer the level (beginner/intermediate/advanced) from context if possible.
- For tech_stack, list individual technologies as separate strings.
- Be exhaustive: extract EVERY legitimate entity mentioned, even if partially described.
- CRITICAL: Do NOT extract the candidate's name, person's name, or document owner as a certification, skill, project, internship, achievement, or academic entity.
- CRITICAL: Do NOT extract generic document headers or document titles (e.g. "Resume", "CV", "Contact Information") as entities.
- Return ONLY the JSON object with no additional text, commentary, or markdown.
"""

_HUMAN_PROMPT = """\
Document text:
---
{document_text}
---

Extract all entities as JSON.
"""


def _extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from LLM response text, handling markdown fences."""
    # Try to find JSON in markdown code fences first
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find the first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from LLM response: {text[:200]}...")


class EntityExtractor:
    """
    Uses Groq LLM with direct JSON parsing to extract typed entities
    from raw document text.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.llm = ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0,
            max_tokens=4096,
        )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", _HUMAN_PROMPT),
        ])
        # Use prompt | llm only — parse JSON manually to avoid
        # langchain-core _type serialization bugs
        self.chain = self.prompt | self.llm

    async def _invoke_and_parse(self, chain, document_text: str) -> dict[str, Any]:
        """Invoke a prompt|llm chain and extract JSON from the response."""
        response = await chain.ainvoke({"document_text": document_text})
        content = response.content if hasattr(response, "content") else str(response)
        return _extract_json(content)

    async def extract(self, document_text: str) -> ExtractionResult:
        """
        Send the document text to the LLM and parse the structured output
        into an ExtractionResult.
        """
        logger.info("Starting LLM entity extraction…")

        # Truncate very long documents to stay within context limits
        max_chars = 60_000
        if len(document_text) > max_chars:
            logger.warning(
                f"Document text truncated from {len(document_text)} to {max_chars} chars"
            )
            document_text = document_text[:max_chars]

        try:
            raw: dict[str, Any] = await self._invoke_and_parse(
                self.chain, document_text
            )
        except Exception as exc:
            logger.warning(
                f"Primary LLM model failed ({exc}). Attempting fallback to llama-3.1-8b-instant..."
            )
            try:
                settings = get_settings()
                fallback_llm = ChatGroq(
                    model="llama-3.1-8b-instant",
                    api_key=settings.groq_api_key,
                    temperature=0,
                    max_tokens=4096,
                )
                fallback_chain = self.prompt | fallback_llm
                raw = await self._invoke_and_parse(
                    fallback_chain, document_text
                )
            except Exception as exc2:
                logger.error(f"LLM extraction fallback failed: {exc2}")
                return ExtractionResult()

        return self._parse_result(raw)

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_result(raw: dict[str, Any]) -> ExtractionResult:
        """Safely parse LLM JSON into typed Pydantic models."""
        def _safe_list(model_cls, items: Any) -> list:
            if not isinstance(items, list):
                return []
            parsed = []
            for item in items:
                try:
                    parsed.append(model_cls(**item))
                except Exception:
                    continue
            return parsed

        result = ExtractionResult(
            certifications=_safe_list(Certification, raw.get("certifications")),
            skills=_safe_list(Skill, raw.get("skills")),
            projects=_safe_list(Project, raw.get("projects")),
            internships=_safe_list(Internship, raw.get("internships")),
            achievements=_safe_list(Achievement, raw.get("achievements")),
            academics=_safe_list(Academic, raw.get("academics")),
        )

        total = (
            len(result.certifications) + len(result.skills) + len(result.projects)
            + len(result.internships) + len(result.achievements) + len(result.academics)
        )
        logger.info(f"Extraction complete — {total} entities found")
        return result
