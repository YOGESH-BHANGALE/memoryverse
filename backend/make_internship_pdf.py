"""
Create a minimal valid PDF for an internship offer letter.
Uses only the stdlib + a hand-built PDF structure (no fpdf2 needed).
"""
import struct, zlib, os

def make_pdf(filename: str, lines: list[str]) -> None:
    """Write a bare-bones but spec-compliant single-page PDF."""
    # Encode text as a PDF content stream
    content_lines = ["BT", "/F1 12 Tf", "50 750 Td", "14 TL"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"({safe}) Tj T*")
    content_lines.append("ET")
    stream_data = "\n".join(content_lines).encode()

    offsets = []
    buf = b"%PDF-1.4\n"

    # obj 1 — catalog
    offsets.append(len(buf))
    buf += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"

    # obj 2 — pages
    offsets.append(len(buf))
    buf += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"

    # obj 3 — page
    offsets.append(len(buf))
    buf += b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"

    # obj 4 — content stream
    offsets.append(len(buf))
    buf += (
        f"4 0 obj\n<< /Length {len(stream_data)} >>\nstream\n".encode()
        + stream_data
        + b"\nendstream\nendobj\n"
    )

    # obj 5 — font
    offsets.append(len(buf))
    buf += b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"

    # xref
    xref_offset = len(buf)
    buf += f"xref\n0 6\n0000000000 65535 f \n".encode()
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()

    # trailer
    buf += (
        f"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    with open(filename, "wb") as f:
        f.write(buf)
    print(f"PDF created: {filename} ({len(buf)} bytes)")


make_pdf("Acme_Corp_Internship_Offer.pdf", [
    "INTERNSHIP OFFER LETTER",
    "",
    "Date: June 1, 2024",
    "To: Yogesh Bhangale",
    "",
    "Dear Yogesh,",
    "",
    "We are pleased to offer you an internship position at Acme Corp",
    "as a Software Engineering Intern in the Platform Engineering team.",
    "",
    "Duration: June 10, 2024 to August 30, 2024 (12 weeks)",
    "Location: Pune, Maharashtra, India (Hybrid)",
    "Stipend: INR 40,000 per month",
    "",
    "Responsibilities:",
    "- Build and maintain internal developer tools using Python and FastAPI",
    "- Contribute to the CI/CD pipeline automation using GitHub Actions",
    "- Participate in agile sprints, code reviews, and design discussions",
    "- Work with PostgreSQL and Redis for backend data management",
    "",
    "Technologies: Python, FastAPI, PostgreSQL, Redis, Docker, GitHub Actions",
    "",
    "Reporting Manager: Ms. Priya Sharma (Lead Engineer)",
    "",
    "Please sign and return this letter by June 5, 2024.",
    "",
    "Sincerely,",
    "HR Department, Acme Corp",
    "hr@acmecorp.example.com",
])
