"""Render the six release PDFs from the retained, editable Word guides."""
import argparse
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table as WordTable
from docx.text.paragraph import Paragraph as WordParagraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
GREEN = colors.HexColor('#16734B')
INK = colors.HexColor('#1F2937')
SOURCES = {
    'ZmalaTerminal-Installation': [('terminal_prep.docx', None)],
    'ZmalaTerminal-Guide': [('terminal_config.docx', 'terminal'), ('terminal_use.docx', None)],
    'ZmalaServer-Installation': [('server_prep.docx', 'server-install')],
    'ZmalaServer-Guide': [('server_prep.docx', 'server-use')],
    'ZmalaPhone-Installation': [('phone_installation.docx', None)],
    'ZmalaPhone-Guide': [('phone_guide.docx', None)],
}
SERVER_INSTALL = {'', 'Before you start', 'Prepare the microSD card',
                  'Install and open administration', 'Keep its address stable',
                  'Replacing an existing server', 'Maintenance and failed installation'}


def selected(section, mode):
    if mode == 'terminal':
        return section != 'Setting up ZmalaPhone'
    if mode == 'server-install':
        return section in SERVER_INSTALL
    if mode == 'server-use':
        return section not in SERVER_INSTALL
    return True


def paragraph_markup(paragraph):
    """Keep external links, including links whose text is absent from older docx APIs."""
    parts = []
    for child in paragraph._p:
        if child.tag not in (qn('w:r'), qn('w:hyperlink')):
            continue
        value = escape(''.join(node.text or '' for node in child.iter(qn('w:t'))))
        if child.tag == qn('w:hyperlink'):
            relation = paragraph.part.rels.get(child.get(qn('r:id')))
            target = str(relation.target_ref) if relation else ''
            if target.startswith(('https://', 'http://')):
                value = '<link href="' + escape(target, {'"': '&quot;'}) + '">' + value + '</link>'
        parts.append(value)
    return ''.join(parts)


def source_blocks(filename, mode, styles):
    doc = Document(ROOT / 'docs' / filename)
    section = ''
    for item in doc.element.body:
        if item.tag == qn('w:p'):
            p = WordParagraph(item, doc)
            style = p.style.name
            if style == 'Title':
                continue
            if style == 'Heading 1':
                section = p.text
            if not selected(section, mode):
                continue
            if filename.startswith('phone_') and p.paragraph_format.page_break_before:
                yield PageBreak()
            markup = paragraph_markup(p)
            if markup:
                key = 'h1' if style == 'Heading 1' else 'h2' if style == 'Heading 2' else 'body'
                if style.startswith('List'):
                    markup = '&#8226; ' + markup
                yield Paragraph(markup, styles[key])
            for blip in item.iter(qn('a:blip')):
                part = doc.part.related_parts.get(blip.get(qn('r:embed')))
                if part is None:
                    continue
                graphic = Image(BytesIO(part.blob))
                factor = min(165 * mm / graphic.imageWidth, 110 * mm / graphic.imageHeight)
                graphic.drawWidth = graphic.imageWidth * factor
                graphic.drawHeight = graphic.imageHeight * factor
                yield graphic
                yield Spacer(1, 5 * mm)
        elif item.tag == qn('w:tbl') and selected(section, mode):
            table = WordTable(item, doc)
            count = len(table.columns)
            rows = [[Paragraph(escape(c.text).replace('\n', '<br/>'), styles['cell'])
                     for c in row.cells] for row in table.rows]
            rendered = Table(rows, colWidths=[165 * mm / count] * count, repeatRows=1, hAlign='LEFT')
            rendered.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E4F1EA')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor('#D9DFDC')),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ]))
            yield rendered
            yield Spacer(1, 5 * mm)


def build(name, destination):
    styles = {
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=10.5, leading=15,
                               textColor=INK, spaceAfter=8, alignment=TA_LEFT),
        'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=15, leading=19,
                             textColor=GREEN, spaceBefore=13, spaceAfter=8, keepWithNext=True),
        'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=11, leading=15,
                             textColor=INK, spaceBefore=8, spaceAfter=6, keepWithNext=True),
        'cell': ParagraphStyle('cell', fontName='Helvetica', fontSize=9.5, leading=13, textColor=INK),
        'title': ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=27, leading=33,
                                textColor=INK, spaceAfter=16),
    }
    title = name.replace('-', ' / ')
    story = [Paragraph(title, styles['title'])]
    for filename, mode in SOURCES[name]:
        story.extend(source_blocks(filename, mode, styles))

    def frame(canvas, document):
        canvas.saveState()
        canvas.setFillColor(GREEN)
        canvas.rect(22 * mm, A4[1] - 18 * mm, 165 * mm, 1.2 * mm, fill=1, stroke=0)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#647168'))
        canvas.drawString(22 * mm, 13 * mm, 'ZmalaCall  |  ' + title)
        canvas.drawRightString(187 * mm, 13 * mm, str(document.page))
        canvas.restoreState()

    SimpleDocTemplate(str(destination / (name + '.pdf')), pagesize=A4,
                      leftMargin=22 * mm, rightMargin=23 * mm, topMargin=25 * mm,
                      bottomMargin=23 * mm, title=title, author='ZmalaCall').build(
                          story, onFirstPage=frame, onLaterPages=frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build_tools/dist/guides')
    parser.add_argument('--component', choices=('terminal', 'server', 'phone'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        if not args.component or name.startswith('Zmala' + args.component.title() + '-'):
            build(name, args.output)
            print(args.output / (name + '.pdf'))


if __name__ == '__main__':
    main()
