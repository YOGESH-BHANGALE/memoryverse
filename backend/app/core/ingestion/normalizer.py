"""
Defensive normalisation of raw LLM extraction output.

The extractor asks Groq for a strict JSON schema, but LLM output drifts in
predictable ways even at temperature 0:

* a list of bare strings instead of objects — ``"skills": ["Python", "Docker"]``
* alternate key names — ``title`` for ``name``, ``organization`` for ``issuer``,
  ``technologies`` for ``tech_stack``
* a comma-joined string where a list is expected — ``"tech_stack": "React, Node"``
* ``null`` / ``{}`` / empty-string entries padding a list
* a plausible entity filed under the wrong top-level key (a degree arriving as a
  certification is the common one)

Previously ``_safe_list`` wrapped ``model_cls(**item)`` in a bare ``except:
continue``, so every one of these shapes was silently *discarded* — the pipeline
never crashed, but the entities vanished. This module coerces instead of
dropping, and runs a reclassification pass so mis-filed entities land in the
right category.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import logger

# Key aliases the LLM substitutes, per entity type. Canonical name -> aliases.
_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "certification": {
        "name": ("title", "certification", "certificate", "cert_name", "course"),
        "issuer": ("organization", "organisation", "issued_by", "provider", "authority", "platform"),
        "date": ("issue_date", "issued", "completion_date", "year", "date_earned"),
        "credential_id": ("credential", "credential_number", "id", "certificate_id", "license_number"),
    },
    "skill": {
        "name": ("skill", "title", "technology", "tech"),
        "level": ("proficiency", "expertise", "competency"),
        "category": ("type", "group", "domain", "skill_type"),
    },
    "project": {
        "name": ("title", "project", "project_name"),
        "description": ("summary", "details", "about"),
        "tech_stack": ("technologies", "tech", "stack", "tools", "tech_used"),
        "date_range": ("dates", "duration", "period", "timeline", "date"),
        "url": ("link", "repo", "repository", "github"),
    },
    "internship": {
        "company": ("organization", "organisation", "employer", "company_name", "firm"),
        "role": ("title", "position", "designation", "job_title"),
        "start_date": ("from", "start", "began"),
        "end_date": ("to", "end", "until", "finished"),
        "description": ("summary", "details", "responsibilities", "work"),
    },
    "achievement": {
        "title": ("name", "achievement", "award", "honour", "honor"),
        "description": ("summary", "details", "about"),
        "date": ("year", "date_awarded", "awarded"),
        "impact": ("result", "outcome", "significance"),
    },
    "academics": {
        "institution": ("school", "college", "university", "organization", "organisation", "institute"),
        "degree": ("qualification", "program", "programme", "course", "name", "title"),
        "start_date": ("from", "start", "admission"),
        "end_date": ("to", "end", "graduation", "completion", "year"),
        "description": ("summary", "details", "grade", "gpa", "cgpa"),
    },
}

# The single field to fill when the LLM hands us a bare string.
_PRIMARY_FIELD = {
    "certification": "name",
    "skill": "name",
    "project": "name",
    "internship": "company",
    "achievement": "title",
    "academics": "institution",
}

_LIST_FIELDS = {"tech_stack"}

# Degrees and academic qualifications. A cert named "Bachelor of Engineering" is
# an academics record, not a certification.
_DEGREE_RE = re.compile(
    r"\b("
    r"bachelor|master|doctor|doctorate|ph\.?\s?d|"
    r"b\.?\s?e\b|b\.?\s?tech|b\.?\s?sc|b\.?\s?c\.?\s?a|b\.?\s?com|b\.?\s?a\b|"
    r"m\.?\s?e\b|m\.?\s?tech|m\.?\s?sc|m\.?\s?c\.?\s?a|m\.?\s?com|m\.?\s?b\.?\s?a|"
    r"h\.?\s?s\.?\s?c|s\.?\s?s\.?\s?c|hsc|ssc|"
    r"higher\s+secondary|senior\s+secondary|secondary\s+school|high\s+school|"
    r"diploma|undergraduate|postgraduate|associate\s+degree"
    r")\b",
    re.IGNORECASE,
)

_INSTITUTION_RE = re.compile(
    r"\b(university|college|institute|institution|school|academy|vidyalaya|polytechnic)\b",
    re.IGNORECASE,
)

# Unambiguous academic-degree words. "Diploma" is deliberately absent: it names
# both a polytechnic/college academic diploma *and* an online course
# certificate ("Diploma in Python", issued by Udemy). On its own it is not
# enough to reclassify a certification as academics — it needs a corroborating
# institution signal (see _reclassify).
_STRONG_DEGREE_RE = re.compile(
    r"\b("
    r"bachelor|master|doctor|doctorate|ph\.?\s?d|"
    r"b\.?\s?e\b|b\.?\s?tech|b\.?\s?sc|b\.?\s?c\.?\s?a|b\.?\s?com|b\.?\s?a\b|"
    r"m\.?\s?e\b|m\.?\s?tech|m\.?\s?sc|m\.?\s?c\.?\s?a|m\.?\s?com|m\.?\s?b\.?\s?a|"
    r"h\.?\s?s\.?\s?c|s\.?\s?s\.?\s?c|hsc|ssc|"
    r"higher\s+secondary|senior\s+secondary|secondary\s+school|high\s+school|"
    r"undergraduate|postgraduate|associate\s+degree"
    r")\b",
    re.IGNORECASE,
)

# Titles that are document furniture, not entities.
_JUNK_TITLES = {
    "resume", "cv", "curriculum vitae", "contact", "contact information",
    "summary", "objective", "profile", "about", "about me", "education",
    "experience", "skills", "projects", "certifications", "achievements",
    "internships", "n/a", "na", "none", "null", "unknown", "not specified",
    "not mentioned", "not available", "-", "--",
}


def _clean_scalar(value: Any) -> Any:
    """Collapse LLM null-ish scalars to None; strip strings."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"n/a", "na", "none", "null", "unknown",
                                        "not specified", "not mentioned",
                                        "not available", "-", "--"}:
            return None
        return text
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        # e.g. {"issuer": {"name": "NPTEL"}} — take the first usable leaf.
        for nested in value.values():
            cleaned = _clean_scalar(nested)
            if cleaned is not None:
                return cleaned
        return None
    if isinstance(value, list):
        parts = [_clean_scalar(v) for v in value]
        joined = ", ".join(p for p in parts if p)
        return joined or None
    return None


def _clean_list(value: Any) -> list[str]:
    """Coerce a tech_stack-style field into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        # "React, Node.js and Postgres" -> ["React", "Node.js", "Postgres"]
        parts = re.split(r"\s*[,;/|]\s*|\s+and\s+", value)
    elif isinstance(value, list):
        parts = []
        for item in value:
            scalar = _clean_scalar(item)
            if scalar:
                parts.extend(re.split(r"\s*[,;/|]\s*", scalar))
    elif isinstance(value, dict):
        parts = [str(k) for k in value]
    else:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = part.strip(" .-")
        if text and text.lower() not in seen and len(text) <= 60:
            out.append(text)
            seen.add(text.lower())
    return out


def normalise_item(kind: str, item: Any) -> dict[str, Any] | None:
    """
    Coerce one raw LLM list element into a dict the Pydantic model accepts.

    Returns None when the element carries no usable content.
    """
    primary = _PRIMARY_FIELD[kind]
    aliases = _ALIASES[kind]

    # A bare string (or number) becomes the entity's primary field.
    if not isinstance(item, dict):
        scalar = _clean_scalar(item)
        return {primary: scalar} if scalar else None

    # Lowercase/underscore the incoming keys so "Tech Stack" matches "tech_stack".
    lowered: dict[str, Any] = {}
    for key, value in item.items():
        norm_key = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
        lowered.setdefault(norm_key, value)

    out: dict[str, Any] = {}
    for canonical, alias_names in aliases.items():
        raw = lowered.get(canonical)
        if raw is None:
            for alias in alias_names:
                if alias in lowered:
                    raw = lowered[alias]
                    break
        if canonical in _LIST_FIELDS:
            out[canonical] = _clean_list(raw)
        else:
            cleaned = _clean_scalar(raw)
            if cleaned is not None:
                out[canonical] = cleaned

    if not out.get(primary):
        # No primary value — try any remaining string as a last resort so a
        # partially-shaped record still survives.
        for value in lowered.values():
            cleaned = _clean_scalar(value)
            if cleaned:
                out[primary] = cleaned
                break

    if not out.get(primary):
        return None
    if str(out[primary]).strip().lower() in _JUNK_TITLES:
        return None
    return out


def normalise_payload(raw: Any) -> dict[str, list[dict[str, Any]]]:
    """
    Normalise a whole extraction payload into per-kind lists of clean dicts,
    then reclassify entries that were filed under the wrong key.
    """
    if not isinstance(raw, dict):
        logger.warning(f"LLM payload was {type(raw).__name__}, not an object — discarding")
        return {kind: [] for kind in _PRIMARY_FIELD}

    # Tolerate singular/alternate top-level keys too.
    key_map = {
        "certifications": ("certification", "certificates", "certs", "courses"),
        "skills": ("skill", "technologies", "technical_skills"),
        "projects": ("project",),
        "internships": ("internship", "experience", "work_experience", "experiences"),
        "achievements": ("achievement", "awards", "honours", "honors"),
        "academics": ("academic", "education", "educations", "qualifications"),
    }
    kinds = {
        "certifications": "certification",
        "skills": "skill",
        "projects": "project",
        "internships": "internship",
        "achievements": "achievement",
        "academics": "academics",
    }

    lowered = {str(k).strip().lower(): v for k, v in raw.items()}

    out: dict[str, list[dict[str, Any]]] = {}
    for plural, kind in kinds.items():
        items = lowered.get(plural)
        if items is None:
            for alias in key_map[plural]:
                if alias in lowered:
                    items = lowered[alias]
                    break
        if isinstance(items, dict):
            items = [items]          # single object where a list was promised
        if not isinstance(items, list):
            items = []

        cleaned = [normalise_item(kind, it) for it in items]
        out[kind] = [c for c in cleaned if c]

    return _reclassify(out)


def _reclassify(buckets: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """
    Move entities the LLM filed under the wrong key into the right bucket.

    Degrees routinely arrive as certifications ("Bachelor of Engineering in
    Computer Science", issuer "Dr. D. Y. Patil Institute of Technology"), which
    is why the certifications collection held academic records.
    """
    moved = 0

    kept_certs: list[dict[str, Any]] = []
    for cert in buckets["certification"]:
        name = str(cert.get("name", ""))
        issuer = str(cert.get("issuer", "") or "")
        # An unambiguous degree word in the name is decisive on its own. The
        # only ambiguous word — "diploma" — is excluded from _STRONG_DEGREE_RE,
        # so it reclassifies only when an institution (university, college,
        # polytechnic…) also appears in the name or issuer. That keeps
        # "Diploma in Python / Udemy" a certification while still catching
        # "Diploma in Mechanical Engineering / Government Polytechnic".
        has_institution = bool(_INSTITUTION_RE.search(f"{name} {issuer}"))
        looks_academic = bool(_STRONG_DEGREE_RE.search(name)) or (
            has_institution and bool(_DEGREE_RE.search(f"{name} {issuer}"))
        )
        if looks_academic:
            buckets["academics"].append({
                "institution": issuer or name,
                "degree": name,
                "end_date": cert.get("date"),
                "description": cert.get("credential_id"),
            })
            moved += 1
        else:
            kept_certs.append(cert)
    buckets["certification"] = kept_certs

    # A degree that arrived as an achievement is also academics.
    kept_achievements: list[dict[str, Any]] = []
    for ach in buckets["achievement"]:
        title = str(ach.get("title", ""))
        if _DEGREE_RE.search(title) and _INSTITUTION_RE.search(title):
            buckets["academics"].append({
                "institution": title,
                "degree": title,
                "end_date": ach.get("date"),
                "description": ach.get("description"),
            })
            moved += 1
        else:
            kept_achievements.append(ach)
    buckets["achievement"] = kept_achievements

    # A "skill" that is really a sentence is a description, not a skill.
    dropped_skills = 0
    kept_skills: list[dict[str, Any]] = []
    for skill in buckets["skill"]:
        name = str(skill.get("name", ""))
        if len(name) > 60 or len(name.split()) > 7:
            dropped_skills += 1
            continue
        kept_skills.append(skill)
    buckets["skill"] = kept_skills

    if moved or dropped_skills:
        logger.info(
            f"Reclassification: {moved} entity(ies) moved to their correct "
            f"category, {dropped_skills} prose 'skill'(s) dropped"
        )
    return buckets
