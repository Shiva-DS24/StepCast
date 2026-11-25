"""Builds step_guide.docx - a printable, step-by-step version of a StepCast lesson
for students who prefer to read and follow along instead of watching the video.

Project:     StepCast - interactive step-by-step screen lessons
Author:      Dr Sivakumar Manickam <skumar@staff.odc.edu.om>
             Head of Educational Technology & Resources, Oman Dental College
Credits:     Conceived, designed, tested and led by Dr Sivakumar Manickam.
             Developed with the help of Claude (Anthropic) as an AI coding assistant.
Version:     1.3
Copyright:   (c) 2026 Dr Sivakumar Manickam. Licensed under the MIT License (see LICENSE).
"""

__author__ = "Dr Sivakumar Manickam"
__email__ = "skumar@staff.odc.edu.om"
__credits__ = ["Dr Sivakumar Manickam (lead: idea, design, testing)", "Claude, Anthropic (AI coding assistant)"]
__version__ = "1.3"
__copyright__ = "(c) 2026 Dr Sivakumar Manickam"


import os

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401  (kept for future landscape option)
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Twips

Twips_4680, Twips_9360 = Twips(4680), Twips(9360)


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _field(paragraph, instr):
    """Insert a Word field such as PAGE or NUMPAGES."""
    run = paragraph.add_run()
    for tag, attr in (("w:fldChar", {"w:fldCharType": "begin"}), ("w:instrText", None),
                      ("w:fldChar", {"w:fldCharType": "separate"}), ("w:t", None),
                      ("w:fldChar", {"w:fldCharType": "end"})):
        el = OxmlElement(tag)
        if attr:
            for k, v in attr.items():
                el.set(qn(k), v)
        elif tag == "w:instrText":
            el.set(qn("xml:space"), "preserve")
            el.text = f" {instr} "
        else:
            el.text = "1"
        run._r.append(el)
    return run


def _shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color.lstrip("#"))
    tcPr.append(shd)


def _no_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblPr.append(borders)


def _picture_border(run, hex_color="D0D5DD"):
    """Thin grey outline around an inline picture."""
    try:
        pic = run._r.xpath(".//pic:pic")[0]
        spPr = pic.xpath("./pic:spPr")[0]
        ln = OxmlElement("a:ln")
        ln.set("w", "9525")
        fill = OxmlElement("a:solidFill")
        clr = OxmlElement("a:srgbClr")
        clr.set("val", hex_color)
        fill.append(clr)
        ln.append(fill)
        spPr.append(ln)
    except Exception:
        pass


def _right_tab(paragraph, pos):
    """Header/Footer styles carry default centre/right tabs; clear them and add ours."""
    ts = paragraph.paragraph_format.tab_stops
    for old in (Cm(8.255), Cm(16.51), Twips_4680, Twips_9360):
        ts.add_tab_stop(old, WD_TAB_ALIGNMENT.CLEAR)
    ts.add_tab_stop(pos, WD_TAB_ALIGNMENT.RIGHT)


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def _no_split(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def _rich_title(paragraph, title):
    """Bold whatever is inside “quotes” (the thing to click or the text to type)."""
    import re
    m = re.fullmatch(r"Press (.+?)( ×\d+)?", title)
    if m:                                   # keyboard shortcut: bold the keys
        paragraph.add_run("Press ")
        paragraph.add_run(m.group(1)).bold = True
        paragraph.add_run((m.group(2) or "") + ".")
        return
    pos = 0
    for m in re.finditer(r"“([^”]*)”", title):
        if m.start() > pos:
            paragraph.add_run(title[pos:m.start()])
        r = paragraph.add_run(m.group(1))
        r.bold = True
        pos = m.end()
    if pos < len(title):
        paragraph.add_run(title[pos:])
    if not title.endswith((".", "!", "?")):
        paragraph.add_run(".")


def _fmt_time(sec):
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def make_step_guide(lesson, out_dir, filename="step_guide.docx"):
    b = lesson.get("branding", {})
    accent = _rgb(b.get("accent", "#0f766e"))
    grey = RGBColor(0x66, 0x70, 0x85)
    app_name = b.get("app_name", "StepCast")
    org = b.get("organisation", "")
    author = b.get("author", "")
    logo = b.get("logo") and os.path.join(out_dir, b["logo"])
    steps = lesson["steps"]

    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2)
    sec.header_distance = sec.footer_distance = Cm(1)
    usable = sec.page_width - sec.left_margin - sec.right_margin

    # ---------- header: logo + StepCast | organisation ........ author
    hdr = sec.header
    hp = hdr.paragraphs[0]
    _right_tab(hp, usable)
    if logo and os.path.exists(logo):
        try:
            hp.add_run().add_picture(logo, height=Cm(0.6))
            hp.add_run("  ")
        except Exception:
            pass
    r = hp.add_run(app_name)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(10), accent
    if org:
        r = hp.add_run(f"  |  {org}")
        r.font.size, r.font.color.rgb = Pt(10), grey
    if author:
        r = hp.add_run(f"\t{author}")
        r.font.size, r.font.color.rgb = Pt(10), grey

    # ---------- footer: lesson title ........ Page X of Y
    fp = sec.footer.paragraphs[0]
    _right_tab(fp, usable)
    for txt in (lesson["title"] + " — step guide", "\tPage "):
        r = fp.add_run(txt)
        r.font.size, r.font.color.rgb = Pt(9), grey
    for instr, txt in (("PAGE", None), (None, " of "), ("NUMPAGES", None)):
        r = _field(fp, instr) if instr else fp.add_run(txt)
        r.font.size, r.font.color.rgb = Pt(9), grey

    # ---------- title block
    p = doc.add_paragraph()
    r = p.add_run(lesson["title"])
    r.bold, r.font.size, r.font.color.rgb = True, Pt(24), accent
    p.paragraph_format.space_after = Pt(2)

    p = doc.add_paragraph()
    by = " · ".join(x for x in (f"Prepared by {author}" if author else "", org) if x)
    r = p.add_run(f"Step-by-step guide · {len(steps)} steps · about {_fmt_time(lesson.get('duration', 0))} of video" + (f" · {by}" if by else ""))
    r.font.size, r.font.color.rgb = Pt(10.5), grey

    if lesson.get("description"):
        doc.add_paragraph(lesson["description"])

    # tip box
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _no_borders(t)
    c = t.rows[0].cells[0]
    _shade(c, "E6F4F2")
    cp = c.paragraphs[0]
    r = cp.add_run("How to use this guide: ")
    r.bold = True
    cp.add_run("do each step in order on your own computer and tick the box when it is done. "
               "Text in bold is exactly what to click or type. Stuck? Open the video lesson "
               "(index.html) and click the same step number to watch it.")
    cp.paragraph_format.space_before = cp.paragraph_format.space_after = Pt(4)
    doc.add_paragraph()

    # ---------- steps table:  #  |  What to do  |  Where  |  ☐
    show_where = any((s.get("note") or "").strip() for s in steps)
    cols = 4 if show_where else 3
    tbl = doc.add_table(rows=1, cols=cols)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    widths = [Cm(1.3), Cm(10.2), Cm(3.6), Cm(1.4)] if show_where else [Cm(1.3), Cm(13.8), Cm(1.4)]
    heads = ["Step", "What to do", "Where", "Done"] if show_where else ["Step", "What to do", "Done"]
    for j, h in enumerate(heads):
        cell = tbl.rows[0].cells[j]
        _shade(cell, b.get("accent", "#0f766e"))
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold, r.font.size, r.font.color.rgb = True, Pt(10.5), RGBColor(0xFF, 0xFF, 0xFF)
        if j != 1:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _repeat_header(tbl.rows[0])

    for i, s in enumerate(steps, 1):
        row = tbl.add_row()
        _no_split(row)
        cells = row.cells
        p = cells[0].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(str(i))
        r.bold, r.font.color.rgb = True, accent
        _rich_title(cells[1].paragraphs[0], s.get("title", ""))
        if show_where:
            r = cells[2].paragraphs[0].add_run((s.get("note") or "").strip())
            r.font.size, r.font.color.rgb = Pt(10), grey
        p = cells[-1].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run("☐")
        r.font.size = Pt(14)
        shot = b.get("guide_screenshots") and s.get("shot") and os.path.join(out_dir, s["shot"])
        if shot and os.path.exists(shot):
            cells[1].add_paragraph().add_run().add_picture(shot, width=Cm(9.5))
        if i % 2 == 0:
            for c in cells:
                _shade(c, "F7F8FA")
    for j, w in enumerate(widths):
        tbl.columns[j].width = w
    for row in tbl.rows:
        for j, w in enumerate(widths):
            row.cells[j].width = w
            for p in row.cells[j].paragraphs:
                p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(3)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(16)
    r = p.add_run("✓ You have completed all the steps.")
    r.bold, r.font.color.rgb = True, accent

    core = doc.core_properties
    core.title = lesson["title"]
    core.author = author or app_name
    core.comments = ("Made with StepCast 1.3 by Dr Sivakumar Manickam (skumar@staff.odc.edu.om), "
                     "developed with the help of Claude (Anthropic).")
    core.subject = "Step-by-step guide"

    path = os.path.join(out_dir, filename)
    doc.save(path)
    return filename
