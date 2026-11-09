"""A small PDF writer for the roadmap and the Transition Report (fpdf2).

Uses the bundled DejaVu Sans (core/fonts, free licence in LICENSE there), because fpdf2's built-in fonts
only cover Latin-1 and the documents contain arrows, middle dots and names in any script. Pure: takes text
and links, returns bytes; no DB and no LLM.
"""
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

FONTS = Path(__file__).parent / "fonts"
FONT = "DejaVu"
TEXT = (30, 41, 59)  # print colours: dark text on white paper (the app's dark theme doesn't print)
MUTED = (100, 116, 139)
LINK = (3, 105, 161)
LINE = 5.5  # body line height, mm


class _PDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font(FONT, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"Page {self.page_no()} of {{nb}}", align="C")


class Document:
    def __init__(self, title: str):
        self.pdf = _PDF(format="A4")
        self.pdf.set_title(title)
        self.pdf.set_creator("AI Career Strategist")
        self.pdf.add_font(FONT, "", str(FONTS / "DejaVuSans.ttf"))
        self.pdf.add_font(FONT, "B", str(FONTS / "DejaVuSans-Bold.ttf"))
        self.pdf.set_auto_page_break(True, margin=18)
        self.pdf.set_margins(18, 18, 18)
        self.pdf.add_page()

    def _text(self, text: str, size: float = 10.5, bold: bool = False, color=TEXT, height: float = LINE,
              indent: float = 0, space_after: float = 0):
        pdf = self.pdf
        pdf.set_font(FONT, "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(pdf.epw - indent, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if space_after:
            pdf.ln(space_after)

    def title(self, text: str) -> None:
        self._text(text, size=18, bold=True, height=9, space_after=1)

    def subtitle(self, text: str) -> None:
        self._text(text, size=10, color=MUTED, space_after=4)

    def h2(self, text: str) -> None:
        if self.pdf.get_y() > self.pdf.h - 50:  # don't leave a heading alone at the bottom of a page
            self.pdf.add_page()
        self.pdf.ln(3)
        self._text(text, size=14, bold=True, height=8, space_after=1)

    def h3(self, text: str) -> None:
        if self.pdf.get_y() > self.pdf.h - 35:
            self.pdf.add_page()
        self.pdf.ln(1.5)
        self._text(text, size=11.5, bold=True, height=6.5)

    def para(self, text: str, muted: bool = False) -> None:
        self._text(text, color=MUTED if muted else TEXT, space_after=1.5)

    def kv(self, label: str, value: str) -> None:
        self._text(f"{label}: {value}")

    def bullet(self, text: str, indent: float = 0) -> None:
        self._text(f"•  {text}", indent=indent)

    def numbered(self, n: int, text: str) -> None:
        self._text(f"{n}.  {text}")

    def check(self, text: str, done: bool, indent: float = 0) -> None:
        self._text(f"{'☑' if done else '☐'}  {text}", indent=indent)

    def link(self, title: str, url: str, note: str = "", indent: float = 0) -> None:
        """A bullet whose title is a clickable link, followed by plain note text."""
        pdf = self.pdf
        pdf.set_x(pdf.l_margin + indent)
        pdf.set_font(FONT, "", 10.5)
        pdf.set_text_color(*TEXT)
        pdf.write(LINE, "•  ")
        pdf.set_text_color(*LINK)
        pdf.write(LINE, title, link=url)
        if note:
            pdf.set_text_color(*MUTED)
            pdf.write(LINE, f"  {note}")
        pdf.ln(LINE)

    def gap(self, mm: float = 2) -> None:
        self.pdf.ln(mm)

    def output(self) -> bytes:
        return bytes(self.pdf.output())
