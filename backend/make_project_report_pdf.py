from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

pdf_path = "Distributed_Stream_Processor_Project_Report.pdf"
doc = SimpleDocTemplate(pdf_path, pagesize=letter)
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    'DocTitle',
    parent=styles['Heading1'],
    fontSize=18,
    spaceAfter=12
)

body_style = styles['Normal']

story = [
    Paragraph("PROJECT REPORT: Distributed Real-Time Stream Processing System", title_style),
    Spacer(1, 10),
    Paragraph("<b>Project Name:</b> StreamPulse Architecture", body_style),
    Paragraph("<b>Date:</b> March 15, 2024", body_style),
    Paragraph("<b>Author:</b> Yogesh Bhangale (Lead Architect)", body_style),
    Spacer(1, 12),
    Paragraph("<b>Executive Summary:</b>", styles['Heading2']),
    Paragraph("The StreamPulse project focused on designing and deploying an enterprise-grade distributed real-time stream processing platform using Apache Kafka, Apache Flink, and Python. The system processes over 100,000 events per second with sub-10ms latency for financial transaction monitoring.", body_style),
    Spacer(1, 10),
    Paragraph("<b>Technical Architecture & Key Contributions:</b>", styles['Heading2']),
    Paragraph("- Architected multi-node Kafka cluster for event ingestion across 4 availability zones.", body_style),
    Paragraph("- Implemented real-time anomaly detection pipelines in Python and Apache Flink.", body_style),
    Paragraph("- Reduced end-to-end processing latency by 45% through custom memory deserialization buffers.", body_style),
    Paragraph("- Integrated Redis for sliding window rate limiting and caching aggregate stats.", body_style),
    Spacer(1, 10),
    Paragraph("<b>Impact & Outcomes:</b>", styles['Heading2']),
    Paragraph("Successfully handled Black Friday traffic peaks with 99.999% uptime, detecting fraud attempts in under 12ms and saving over $1.2M in potential losses.", body_style)
]

doc.build(story)
print(f"Created {pdf_path} successfully.")
