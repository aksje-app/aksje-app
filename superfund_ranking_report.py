"""Portable, read-only ranking report exports from the frozen Superfond digest."""
from io import BytesIO
from html import escape
from superfund_ranking_digest import pages

def report_text(digest):
    return "\n\n".join(pages(digest, max_chars=2500))

def report_pdf(digest):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pathlib import Path
    fonts=Path(__file__).resolve().parent/"assets/fonts"
    for name,filename in (("NotoSuperRank","NotoSans-Regular.ttf"),("NotoSuperRankBold","NotoSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,str(fonts/filename)))
    styles=getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName="NotoSuperRankBold" if style.name in ("Title","Heading2") else "NotoSuperRank"
        if hasattr(style, "leading") and hasattr(style, "fontSize"):
            style.leading = max(style.leading, style.fontSize * 1.35)
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=40,rightMargin=40,topMargin=44,bottomMargin=42)
    story=[Paragraph("Superfond – rangering",styles["Title"]),Spacer(1,12)]
    for block in pages(digest,max_chars=6000):
        for line in block.splitlines():
            if not line.strip():
                story.append(Spacer(1,8))
            else:
                story.append(Paragraph(escape(line),styles["BodyText"]))
                story.append(Spacer(1,4))
    doc.build(story)
    return out.getvalue()
