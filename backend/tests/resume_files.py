"""Small resume files built in memory for tests."""
import io

import docx


def make_docx(paragraphs, table=None) -> bytes:
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    if table:
        t = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def make_pdf(lines) -> bytes:
    """A one-page PDF with the lines as real text (Helvetica), with a correct xref table.
    No lines gives a page without any text, like a scanned resume."""
    ops = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")
        ops += [f"({escaped}) Tj", "T*"]
    ops.append("ET")
    stream = "\n".join(ops).encode() if lines else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


RESUME_LINES = [
    "Jane Doe",
    "Senior Backend Engineer, Acme Payments, 2019-03 to Present",
    "Software Engineer, Globex, 2015-06 to 2019-02",
    "Skills: Python, PostgreSQL, Kafka, AWS",
    "Certifications: AWS Certified Developer",
    "BSc Computer Science, State University, 2015",
]
