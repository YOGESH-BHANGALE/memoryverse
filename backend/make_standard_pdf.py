def build_pypdf2_compatible_pdf(filename, title, lines):
    stream = "BT /F1 12 Tf 50 750 Td 16 TL\n"
    escaped_title = title.replace("(", "\\(").replace(")", "\\)")
    stream += f"({escaped_title}) Tj T*\n"
    for l in lines:
        escaped = l.replace("(", "\\(").replace(")", "\\)")
        stream += f"({escaped}) Tj T*\n"
    stream += "ET\n"
    
    stream_bytes = stream.encode("latin1")
    stream_len = len(stream_bytes)
    
    header = b"%PDF-1.4\n"
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    obj4 = f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("latin1") + stream_bytes + b"\nendstream\nendobj\n"
    obj5 = b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    
    body = obj1 + obj2 + obj3 + obj4 + obj5
    
    offsets = [0, len(header)]
    curr = len(header)
    for o in [obj1, obj2, obj3, obj4]:
        curr += len(o)
        offsets.append(curr)
        
    xref_offset = len(header) + len(body)
    
    xref = f"xref\n0 6\n0000000000 65535 f \n".encode("ascii")
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n".encode("ascii")
        
    trailer = f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    
    with open(filename, "wb") as f:
        f.write(header + body + xref + trailer)

lines = [
    "This is to certify that YOGESH BHANGALE",
    "has successfully completed all requirements for",
    "Google Cloud Certified - Professional Cloud Architect",
    "Issue Date: October 10, 2024",
    "Credential ID: GCP-99881122",
    "Skills Verified: Google Cloud Platform, Kubernetes, GKE, Terraform, Cloud Security"
]

build_pypdf2_compatible_pdf("Google_Cloud_Certified_Architect.pdf", "GOOGLE CLOUD CERTIFICATION", lines)
print("PDF created successfully!")
