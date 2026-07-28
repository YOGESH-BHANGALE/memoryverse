"""
General-purpose utility helpers.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from app.models.schemas import FileType


def generate_job_id() -> str:
    """Return a new unique job identifier."""
    return str(uuid4())


def detect_file_type(filename: str) -> FileType:
    """Determine file type from extension."""
    ext = Path(filename).suffix.lower().lstrip(".")
    mapping = {"pdf": FileType.PDF, "txt": FileType.TXT, "docx": FileType.DOCX}
    if ext not in mapping:
        raise ValueError(f"Unsupported file type: .{ext}")
    return mapping[ext]


_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def normalise_date(raw: str | None) -> str | None:
    """
    Best-effort normalisation of free-text dates into YYYY-MM format.
    Returns None if parsing fails entirely.
    """
    if not raw:
        return None

    raw = raw.strip()

    # Already YYYY-MM
    if re.match(r"^\d{4}-\d{2}$", raw):
        return raw

    # YYYY-MM-DD → YYYY-MM
    m = re.match(r"^(\d{4})-(\d{2})-\d{2}$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # "Month YYYY" or "Mon YYYY"
    m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", raw)
    if m:
        month_str = m.group(1)[:3].lower()
        if month_str in _MONTH_MAP:
            return f"{m.group(2)}-{_MONTH_MAP[month_str]}"

    # "YYYY" alone → YYYY-01
    m = re.match(r"^(\d{4})$", raw)
    if m:
        return f"{m.group(1)}-01"

    return None


def sanitise_filename(name: str) -> str:
    """Remove dangerous characters from a filename."""
    return re.sub(r"[^\w.\-]", "_", name)
