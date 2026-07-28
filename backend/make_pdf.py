# Pure python minimalist PDF generator without external dependencies
def make_simple_pdf(filename, text_lines):
    stream_content = "BT\n/F1 12 Tf\n50 750 Td\n16 TL\n"
    for line in text_lines:
        # escape parens
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_content += f"({escaped}) T*\n"
    stream_content += "ET\n"
    
    stream_bytes = stream_content.encode("latin1")
    stream_len = len(stream_bytes)
    
    pdf = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length {stream_len} >>
stream
{stream_content}endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000060 00000 n 
0000000117 00000 n 
0000000249 00000 n 
0000000300 + 050 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
400
%%EOF
"""
    with open(filename, "wb") as f:
        f.write(pdf.encode("latin1"))

lines = [
    "GOOGLE CLOUD CERTIFICATION",
    "",
    "This is to certify that YOGESH BHANGALE",
    "has successfully completed all requirements for",
    "Google Cloud Certified - Professional Cloud Architect",
    "",
    "Issue Date: October 10, 2024",
    "Credential ID: GCP-99881122",
    "Skills Verified: Google Cloud Platform, Kubernetes GKE, Terraform, Cloud Security"
]

make_simple_pdf("Google_Cloud_Professional_Cloud_Architect.pdf", lines)
print("PDF created successfully without heavy libraries!")
