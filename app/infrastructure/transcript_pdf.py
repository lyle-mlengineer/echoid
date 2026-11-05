"""Lays out an EchoID transcript as a branded PDF, styled after the site."""

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas

PAGE_WIDTH, PAGE_HEIGHT = letter
SIDE_MARGIN = 56
CONTENT_WIDTH = PAGE_WIDTH - 2 * SIDE_MARGIN

BAND_HEIGHT = 96
SLIM_BAND_HEIGHT = 44
CONTENT_BOTTOM = 86
FOOTER_RULE_Y = 58
FOOTER_BASELINE = 42

PAPER = HexColor("#fbfcf9")
TEAL = HexColor("#07877c")
TEAL_DARK = HexColor("#063e3b")
TEAL_DEEP = HexColor("#032f2d")
TEAL_PALE = HexColor("#e7f5f2")
GOLD = HexColor("#ffba08")
MUTED = HexColor("#718583")
BODY = HexColor("#4a655d")
FAINT = HexColor("#a0afa8")
LINE = HexColor("#e5eeea")
HAIRLINE = HexColor("#edf2ee")
ON_TEAL = HexColor("#d9f2ec")
WHITE = HexColor("#ffffff")
DIM_ON_TEAL = HexColor("#9fd6cd")
RING_ON_TEAL = HexColor("#1f9a8d")

# --speaker-accent / --speaker-tint pairs from static/css/styles.css
SPEAKER_TONES = (
    (HexColor("#168875"), HexColor("#f0f8f4")),
    (HexColor("#8a63b6"), HexColor("#f7f2fb")),
    (HexColor("#c27a2c"), HexColor("#fff7ec")),
    (HexColor("#4a78b8"), HexColor("#f0f5fc")),
    (HexColor("#be5f72"), HexColor("#fff2f4")),
    (HexColor("#63843e"), HexColor("#f5f8ee")),
)

REGULAR = "Helvetica"
BOLD = "Helvetica-Bold"

MADE_BY = "Made by Lyle Okoth"
AUTHOR = "Lyle Okoth"
TAGLINE = "Every voice, heard clearly."
SIGNATURE = "Diarized with EchoID, the speaker-labelled transcript studio."


def speaker_tones(segments: list[dict]) -> dict[str, int]:
    """Assign tone indices in first-appearance order, matching the studio rows."""
    tones: dict[str, int] = {}
    for segment in segments:
        tones.setdefault(segment["speaker"], len(tones) % len(SPEAKER_TONES))
    return tones


def clock(seconds: object) -> str:
    total = max(0, int(seconds or 0))
    return f"{total // 60}:{total % 60:02d}"


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    for chunk in str(text).splitlines() or [""]:
        current = ""
        for word in chunk.split():
            candidate = f"{current} {word}" if current else word
            if stringWidth(candidate, font, size) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            while stringWidth(current, font, size) > width:
                cut = len(current)
                while cut > 1 and stringWidth(current[:cut], font, size) > width:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        if current:
            lines.append(current)
    return lines or [""]


def clip(text: str, font: str, size: float, width: float) -> str:
    if stringWidth(text, font, size) <= width:
        return text
    clipped = text
    while clipped and stringWidth(f"{clipped}…", font, size) > width:
        clipped = clipped[:-1]
    return f"{clipped}…"


def _mark(pdf: pdfcanvas.Canvas, x: float, y: float, size: float) -> None:
    """The gold brand square with the lowercase 'e' from the site header."""
    pdf.saveState()
    pdf.setFillColor(GOLD)
    pdf.roundRect(x, y, size, size, size * 0.33, stroke=0, fill=1)
    pdf.setFillColor(TEAL_DARK)
    pdf.setFont(BOLD, size * 0.62)
    pdf.drawCentredString(x + size / 2, y + size * 0.3, "e")
    pdf.restoreState()


def _footer(pdf: pdfcanvas.Canvas, page: int, total: int) -> None:
    pdf.saveState()
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.7)
    pdf.line(SIDE_MARGIN, FOOTER_RULE_Y, PAGE_WIDTH - SIDE_MARGIN, FOOTER_RULE_Y)
    _mark(pdf, SIDE_MARGIN, FOOTER_BASELINE - 4, 12)
    x = SIDE_MARGIN + 12 + 9
    pdf.setFont(BOLD, 8)
    pdf.setFillColor(TEAL_DARK)
    pdf.drawString(x, FOOTER_BASELINE, "EchoID")
    x += stringWidth("EchoID", BOLD, 8) + 7
    pdf.setFont(REGULAR, 8)
    pdf.setFillColor(MUTED)
    pdf.drawString(x, FOOTER_BASELINE, f"· {TAGLINE} · {MADE_BY}")
    pdf.setFont(REGULAR, 8)
    pdf.setFillColor(FAINT)
    pdf.drawRightString(PAGE_WIDTH - SIDE_MARGIN, FOOTER_BASELINE, f"Page {page} of {total}")
    pdf.restoreState()


class _PageFooterCanvas(pdfcanvas.Canvas):
    """Adds the brand footer once the total page count is known."""

    def __init__(self, buffer: io.BytesIO, **kwargs) -> None:
        super().__init__(buffer, **kwargs)
        self._pages: list[dict] = []

    def showPage(self) -> None:
        self._pages.append(self._snapshot())
        self._startPage()

    def _snapshot(self) -> dict:
        state = dict(self.__dict__)
        state.pop("_pages", None)
        return state

    def save(self) -> None:
        self._pages.append(self._snapshot())
        total = len(self._pages)
        for index, state in enumerate(self._pages, start=1):
            self.__dict__.update(state)
            _footer(self, index, total)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)


def _tracked(
    pdf: pdfcanvas.Canvas,
    x: float,
    y: float,
    text: str,
    font: str,
    size: float,
    color: HexColor,
    spacing: float,
    right: bool = False,
) -> None:
    """Draws a label with letter-spacing, which canvas.drawString cannot do."""
    width = stringWidth(text, font, size) + spacing * max(len(text) - 1, 0)
    text_object = pdf.beginText(x - width if right else x, y)
    text_object.setFont(font, size)
    text_object.setFillColor(color)
    text_object.setCharSpace(spacing)
    text_object.textOut(text)
    pdf.drawText(text_object)


def _paper(pdf: pdfcanvas.Canvas) -> None:
    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)


def _title_band(pdf: pdfcanvas.Canvas, exported_on: str) -> None:
    top = PAGE_HEIGHT - BAND_HEIGHT
    pdf.setFillColor(TEAL)
    pdf.rect(0, top, PAGE_WIDTH, BAND_HEIGHT, stroke=0, fill=1)
    pdf.saveState()
    band = pdf.beginPath()
    band.rect(0, top, PAGE_WIDTH, BAND_HEIGHT)
    pdf.clipPath(band, stroke=0, fill=0)
    pdf.setStrokeColor(RING_ON_TEAL)
    pdf.setLineWidth(1)
    pdf.circle(PAGE_WIDTH - 70, PAGE_HEIGHT - 6, 96, stroke=1, fill=0)
    pdf.circle(PAGE_WIDTH + 40, top - 66, 130, stroke=1, fill=0)
    pdf.restoreState()
    _mark(pdf, SIDE_MARGIN, PAGE_HEIGHT - 56, 30)
    _tracked(pdf, SIDE_MARGIN + 41, PAGE_HEIGHT - 51, "EchoID", BOLD, 20, WHITE, -0.5)
    _tracked(pdf, SIDE_MARGIN + 41, PAGE_HEIGHT - 66, TAGLINE.upper(), BOLD, 8, ON_TEAL, 1.6)
    _tracked(pdf, PAGE_WIDTH - SIDE_MARGIN, PAGE_HEIGHT - 44, "SPEAKER-DIARIZED", BOLD, 8, ON_TEAL, 1.6, right=True)
    _tracked(pdf, PAGE_WIDTH - SIDE_MARGIN, PAGE_HEIGHT - 58, "TRANSCRIPT", BOLD, 8, ON_TEAL, 1.6, right=True)
    pdf.setFont(REGULAR, 7.5)
    pdf.setFillColor(DIM_ON_TEAL)
    pdf.drawRightString(PAGE_WIDTH - SIDE_MARGIN, PAGE_HEIGHT - 74, exported_on)


def _continuation_band(pdf: pdfcanvas.Canvas, title: str) -> None:
    top = PAGE_HEIGHT - SLIM_BAND_HEIGHT
    pdf.setFillColor(TEAL)
    pdf.rect(0, top, PAGE_WIDTH, SLIM_BAND_HEIGHT, stroke=0, fill=1)
    _mark(pdf, SIDE_MARGIN, top + 13, 18)
    pdf.setFillColor(HexColor("#ffffff"))
    pdf.setFont(BOLD, 12)
    pdf.drawString(SIDE_MARGIN + 27, top + 16, "EchoID")
    pdf.setFont(REGULAR, 8)
    pdf.setFillColor(ON_TEAL)
    pdf.drawRightString(PAGE_WIDTH - SIDE_MARGIN, top + 17, clip(title, REGULAR, 8, 260))


def _headings(pdf: pdfcanvas.Canvas, heading: dict) -> float:
    _tracked(pdf, SIDE_MARGIN, 662, clip(heading["title"], BOLD, 19, CONTENT_WIDTH), BOLD, 19, TEAL_DEEP, -0.3)
    pdf.setFillColor(GOLD)
    pdf.rect(SIDE_MARGIN, 650, 46, 3, stroke=0, fill=1)
    pdf.setFont(REGULAR, 8.6)
    pdf.setFillColor(MUTED)
    pdf.drawString(SIDE_MARGIN, 634, heading["meta"])
    y = 620
    if heading["filter_note"]:
        pdf.setFont(REGULAR, 8.2)
        pdf.setFillColor(TEAL)
        pdf.drawString(SIDE_MARGIN, y, clip(heading["filter_note"], REGULAR, 8.2, CONTENT_WIDTH))
        y -= 14
    pdf.setStrokeColor(HAIRLINE)
    pdf.setLineWidth(0.8)
    pdf.line(SIDE_MARGIN, y - 4, PAGE_WIDTH - SIDE_MARGIN, y - 4)
    return y - 20


def _lines(segment: dict) -> list[str]:
    return wrap(segment["text"], REGULAR, 10, CONTENT_WIDTH - 44)


def _card_height(segment: dict) -> float:
    return 53 + 14.5 * (len(_lines(segment)) - 1)


def _block_height(segment: dict) -> float:
    return _card_height(segment) + 11


def _segment(pdf: pdfcanvas.Canvas, segment: dict, tone: int, top: float) -> float:
    accent, tint = SPEAKER_TONES[tone]
    text_x = SIDE_MARGIN + 22
    lines = _lines(segment)
    height = _card_height(segment)

    pdf.setFillColor(tint)
    pdf.roundRect(SIDE_MARGIN, top - height, CONTENT_WIDTH, height, 8, stroke=0, fill=1)
    pdf.setFillColor(accent)
    pdf.roundRect(SIDE_MARGIN + 8, top - height + 9, 3, height - 18, 1.5, stroke=0, fill=1)

    name = str(segment["speaker"])
    pdf.setFont(BOLD, 8.6)
    pdf.setFillColor(accent)
    pdf.drawString(text_x, top - 20, name)
    pdf.setFont(REGULAR, 7.4)
    pdf.setFillColor(FAINT)
    label = f"{clock(segment['start_seconds'])} – {clock(segment['end_seconds'])}"
    pdf.drawString(text_x + stringWidth(name, BOLD, 8.6) + 8, top - 20, label)

    pdf.setFont(REGULAR, 10)
    pdf.setFillColor(BODY)
    baseline = top - 37
    for line in lines:
        pdf.drawString(text_x, baseline, line)
        baseline -= 14.5
    return top - height - 11


def _signature(pdf: pdfcanvas.Canvas, top: float, reference: str) -> float:
    height = 62
    pdf.setFillColor(TEAL_PALE)
    pdf.roundRect(SIDE_MARGIN, top - height, CONTENT_WIDTH, height, 10, stroke=0, fill=1)
    _mark(pdf, SIDE_MARGIN + 16, top - 42, 26)
    pdf.setFont(BOLD, 11.5)
    pdf.setFillColor(TEAL_DEEP)
    pdf.drawString(111, top - 27, MADE_BY)
    pdf.setFont(REGULAR, 8.2)
    pdf.setFillColor(MUTED)
    pdf.drawString(111, top - 42, f"{SIGNATURE} {TAGLINE}")
    pdf.setFont(REGULAR, 7.2)
    pdf.setFillColor(FAINT)
    pdf.drawRightString(PAGE_WIDTH - SIDE_MARGIN - 14, top - 27, f"echoid · {reference[:8]}")
    return top - height - 16


def render_transcript_pdf(
    segments: list[dict],
    tones: dict[str, int],
    *,
    title: str,
    meta: str,
    filter_note: str,
    reference: str,
    exported_on: str,
) -> bytes:
    buffer = io.BytesIO()
    pdf = _PageFooterCanvas(buffer, pagesize=letter)
    pdf.setTitle(f"EchoID transcript - {title}")
    pdf.setAuthor(AUTHOR)
    pdf.setCreator("EchoID")
    pdf.setSubject("Speaker-diarized audio transcript")
    pdf.setKeywords(["EchoID", "transcript", "speaker diarization", MADE_BY])

    _paper(pdf)
    _title_band(pdf, exported_on)
    y = _headings(pdf, {"title": title, "meta": meta, "filter_note": filter_note})
    if not segments:
        pdf.setFont(REGULAR, 9.5)
        pdf.setFillColor(MUTED)
        pdf.drawString(SIDE_MARGIN, y, "No transcript lines match the current filters.")
        y -= 24

    for segment in segments:
        if y - _block_height(segment) < CONTENT_BOTTOM:
            pdf.showPage()
            _paper(pdf)
            _continuation_band(pdf, title)
            y = PAGE_HEIGHT - SLIM_BAND_HEIGHT - 30
        y = _segment(pdf, segment, tones.get(segment["speaker"], 0), y)

    if y - 62 < CONTENT_BOTTOM:
        pdf.showPage()
        _paper(pdf)
        _continuation_band(pdf, title)
        y = PAGE_HEIGHT - SLIM_BAND_HEIGHT - 30
    _signature(pdf, y, reference)
    pdf.save()
    return buffer.getvalue()
