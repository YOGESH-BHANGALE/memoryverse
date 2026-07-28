import sys

# Create a clean, valid PDF file using pure python binary structure
def build_valid_pdf(filename):
    text = (
        "GOOGLE CLOUD CERTIFICATION\n\n"
        "This is to certify that YOGESH BHANGALE\n"
        "has successfully completed all requirements for\n"
        "Google Cloud Certified - Professional Cloud Architect\n\n"
        "Issue Date: October 10, 2024\n"
        "Credential ID: GCP-99881122\n"
        "Skills Verified: Google Cloud Platform, Kubernetes, GKE, Terraform, Cloud Security"
    )
    
    lines = text.split("\n")
    stream_content = "BT /F1 12 Tf 50 700 Td 18 TL "
    for l in lines:
        escaped = l.replace("(", "\\(").replace(")", "\\)")
        stream_content += f"({escaped}) T* "
    stream_content += "ET"
    
    stream_data = stream_content.encode("ascii")
    stream_len = len(stream_data)
    
    header = b"%PDF-1.4\n"
    
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    obj4 = f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("ascii") + stream_data + b"\nendstream\nendobj\n"
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

build_valid_pdf("Google_Cloud_Certified_Architect.pdf")
print("Valid PDF generated successfully!")
