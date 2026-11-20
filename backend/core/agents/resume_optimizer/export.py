"""PDF and DOCX exports of a tailored resume (pure: no DB, no LLM). Only the resume itself: no highlights and
no "To add" list. Sections in the same order as assemble.to_text."""
from io import BytesIO

from docx import Document as Docx
from docx.shared import Pt

from core.agents.resume_optimizer.assemble import plain
from core.agents.resume_optimizer.schemas import ResumeDoc
from core.pdf import Document


def _sections(doc: ResumeDoc) -> list[tuple[str, list[tuple[str, list[str]]]]]:
    """(heading, [(line, bullets)]) for every non-empty section."""
    out = []
    if doc.summary:
        out.append(("Summary", [(plain(doc.summary), [])]))
    if doc.roles:
        out.append(("Experience", [(f"{r.title} · {r.employer} · {r.dates}", [plain(h) for h in r.highlights])
                                   for r in doc.roles]))
    if doc.projects:
        out.append(("Projects", [(f"{p.title} (dataset: {p.dataset})", [plain(b) for b in p.bullets])
                                 for p in doc.projects]))
    if doc.skills:
        out.append(("Skills", [(", ".join(s.name for s in doc.skills), [])]))
    if doc.achievements:
        out.append(("Achievements", [("", doc.achievements)]))
    if doc.courses:
        out.append(("Courses and Professional Development", [("", [f"{c.title}, {c.provider}" for c in doc.courses])]))
    if doc.education:
        out.append(("Education", [("", doc.education)]))
    if doc.certifications:
        out.append(("Certifications", [("", doc.certifications)]))
    return out


def _subtitle(doc: ResumeDoc) -> str:
    return " · ".join(x for x in (plain(doc.headline), doc.email) if x)


def to_pdf(doc: ResumeDoc) -> bytes:
    pdf = Document(f"{doc.name} resume")
    pdf.title(doc.name)
    pdf.subtitle(_subtitle(doc))
    for heading, entries in _sections(doc):
        pdf.h2(heading)
        for line, bullets in entries:
            if line and bullets:
                pdf.h3(line)
            elif line:
                pdf.para(line)
            for b in bullets:
                pdf.bullet(b)
    return pdf.output()


def to_docx(doc: ResumeDoc) -> bytes:
    d = Docx()
    d.styles["Normal"].font.size = Pt(10.5)
    d.add_heading(doc.name, level=0)
    d.add_paragraph(_subtitle(doc))
    for heading, entries in _sections(doc):
        d.add_heading(heading, level=1)
        for line, bullets in entries:
            if line and bullets:
                d.add_paragraph().add_run(line).bold = True
            elif line:
                d.add_paragraph(line)
            for b in bullets:
                d.add_paragraph(b, style="List Bullet")
    out = BytesIO()
    d.save(out)
    return out.getvalue()
