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
from app.core.ingestion.normalizer import normalise_payload
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


def _repair_truncated_json(text: str) -> dict[str, Any] | None:
    """
    Salvage a JSON object that was cut off mid-stream.

    Hitting max_tokens on a long resume yields valid JSON right up to the
    truncation point and nothing after it. Rather than lose the whole
    extraction, walk back to the last complete element and close the open
    brackets so the prefix parses.
    """
    start = text.find("{")
    if start == -1:
        return None
    body = text[start:]

    # Trim to the last plausible element boundary, then close what is open.
    for cut in range(len(body), 0, -1):
        if body[cut - 1] not in "}]\"0123456789truefalsnl ":
            continue
        candidate = body[:cut].rstrip().rstrip(",")

        depth_curly = depth_square = 0
        in_string = escaped = False
        for ch in candidate:
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth_curly += 1
            elif ch == "}":
                depth_curly -= 1
            elif ch == "[":
                depth_square += 1
            elif ch == "]":
                depth_square -= 1

        if in_string or depth_curly < 0 or depth_square < 0:
            continue

        patched = candidate + ("]" * depth_square) + ("}" * depth_curly)
        try:
            parsed = json.loads(patched)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            logger.warning(
                f"Recovered truncated LLM JSON — salvaged {cut}/{len(body)} chars"
            )
            return parsed
    return None


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

    # Last resort: the response was cut off mid-object — salvage the prefix
    # instead of throwing the entire extraction away.
    repaired = _repair_truncated_json(text)
    if repaired is not None:
        return repaired

    raise ValueError(f"Could not extract valid JSON from LLM response: {text[:200]}...")


class EntityExtractor:
    """
    Uses Groq LLM with direct JSON parsing to extract typed entities
    from raw document text.

    Model selection is resilient by construction. Groq retires models without
    notice — ``llama-3.3-70b-versatile`` started returning 404 model_not_found
    in production — and the configured model can be overridden by a ``GROQ_MODEL``
    environment variable that points at a now-dead model, a value we cannot edit
    from code. So instead of one model with a single fallback, extraction walks an
    ordered list of candidates and uses the first that answers: the configured
    primary, the configured fallback, then hardcoded known-good defaults that no
    env var can clobber. Only if *every* candidate fails do we give up (loudly),
    so a single retirement can never silently zero out extraction again.
    """

    # Last-resort models, tried after the configured ones. These are hardcoded
    # precisely so a bad GROQ_MODEL / GROQ_FALLBACK_MODEL env var cannot remove
    # them from the chain. Update only to models confirmed live via
    # GET https://api.groq.com/openai/v1/models.
    _SAFETY_NET_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")

    def __init__(self) -> None:
        settings = get_settings()
        # Ordered and de-duplicated: configured primary, configured fallback,
        # then the safety net. Deliberately spans more than one model family so
        # one provider-side retirement or rate-limit can't take out the whole
        # chain.
        self._models: list[str] = []
        seen: set[str] = set()
        for model in (
            settings.groq_model,
            settings.groq_fallback_model,
            *self._SAFETY_NET_MODELS,
        ):
            if model and model not in seen:
                seen.add(model)
                self._models.append(model)

        self._api_key = settings.groq_api_key
        self._llm_cache: dict[str, ChatGroq] = {}
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", _HUMAN_PROMPT),
        ])

    def _chain_for(self, model: str):
        """Build (and memoise) a prompt|llm chain for one model.

        Parse JSON manually rather than piping through an output parser to avoid
        langchain-core ``_type`` serialization bugs.
        """
        llm = self._llm_cache.get(model)
        if llm is None:
            llm = ChatGroq(
                model=model,
                api_key=self._api_key,
                temperature=0,
                max_tokens=4096,
            )
            self._llm_cache[model] = llm
        return self.prompt | llm

    async def _invoke_and_parse(self, chain, document_text: str) -> dict[str, Any]:
        """Invoke a prompt|llm chain and extract JSON from the response."""
        response = await chain.ainvoke({"document_text": document_text})
        content = response.content if hasattr(response, "content") else str(response)
        return _extract_json(content)

    async def extract(self, document_text: str) -> ExtractionResult:
        """
        Send the document text to the LLM and parse the structured output
        into an ExtractionResult, walking the candidate models until one answers.
        """
        logger.info("Starting LLM entity extraction…")

        # Truncate very long documents to stay within context limits
        max_chars = 60_000
        if len(document_text) > max_chars:
            logger.warning(
                f"Document text truncated from {len(document_text)} to {max_chars} chars"
            )
            document_text = document_text[:max_chars]

        last_error: Exception | None = None
        for idx, model in enumerate(self._models):
            try:
                raw: dict[str, Any] = await self._invoke_and_parse(
                    self._chain_for(model), document_text
                )
            except Exception as exc:
                last_error = exc
                remaining = len(self._models) - idx - 1
                logger.warning(
                    f"Extraction model {model} failed ({type(exc).__name__}: {exc}). "
                    + (f"Trying next candidate ({remaining} left)…" if remaining else "No candidates left.")
                )
                continue

            if idx > 0:
                logger.warning(
                    f"Extraction succeeded on fallback model {model} "
                    f"(candidate #{idx + 1} of {len(self._models)}) — "
                    f"check the configured GROQ_MODEL is still served."
                )
            return self._parse_result(raw)

        logger.error(
            f"All {len(self._models)} extraction candidate models failed "
            f"({', '.join(self._models)}); returning empty result. "
            f"Last error: {last_error}"
        )
        return ExtractionResult()

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_result(raw: dict[str, Any]) -> ExtractionResult:
        """
        Safely parse LLM JSON into typed Pydantic models.

        The raw payload is normalised first (see core.ingestion.normalizer):
        bare strings, aliased keys and comma-joined lists are coerced into the
        expected shape rather than discarded, and entities filed under the
        wrong key are reclassified. Only genuinely unusable records are dropped.
        """
        buckets = normalise_payload(raw)

        def _build(model_cls, kind: str) -> list:
            parsed = []
            for item in buckets.get(kind, []):
                try:
                    parsed.append(model_cls(**item))
                except Exception as exc:
                    logger.warning(f"Dropping unparseable {kind} record {item!r}: {exc}")
            return parsed

        result = ExtractionResult(
            certifications=_build(Certification, "certification"),
            skills=_build(Skill, "skill"),
            projects=_build(Project, "project"),
            internships=_build(Internship, "internship"),
            achievements=_build(Achievement, "achievement"),
            academics=_build(Academic, "academics"),
        )

        total = (
            len(result.certifications) + len(result.skills) + len(result.projects)
            + len(result.internships) + len(result.achievements) + len(result.academics)
        )
        logger.info(f"Extraction complete — {total} entities found")
        return result
