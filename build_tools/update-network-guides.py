"""Append the secure-network operator notes to the retained Word user guides.

Run with the document workspace runtime. Existing guide structure is preserved;
this section is replaced by title on subsequent runs.
"""
from pathlib import Path
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = {
 'server_prep.docx': [
  'Calls from networks that block UDP',
  'The normal installation serves the local network. For terminals in separate buildings, ask the network administrator to configure secure relay mode before printing the server QR codes.',
  'This mode uses encrypted connections on TCP port 443 for server configuration, call signalling and the media relay. It needs public endpoints, trusted certificates and a TURN relay. The technical setup and port mapping are described in docs/server.md. It is not enabled automatically by the installer.',
  'After the administrator enables secure mode, use the HTTPS administration address and print new server QR codes. Enroll both terminals with these codes. Keep the private relay secret and certificate keys in a separate secure backup; the account backup does not include them.',
  'Make a call in each direction and check sound and moving video before handing over the terminals. A network that allows only web browsing through a proxy can still block calls. Give its administrator the three configured endpoint names and request direct TLS access on TCP port 443.'
 ],
 'terminal_config.docx': [
  'Using a secure server connection',
  'If the terminal will be used on a network that blocks UDP, ask the server administrator for an HTTPS server QR code. The administrator must first configure the secure call service and media relay.',
  'Install the current terminal software, then use Settings and Reset to enroll with the new QR code. An old HTTP QR code cannot activate secure relay mode. Do not turn off certificate checks to work around an enrollment error.',
  'Call and answer controls stay the same. The terminal receives temporary relay credentials from the server. It updates them while idle, so an active call is not interrupted. If the terminal has been offline for a long time, restore its server connection before making a call.',
  'Before use, make a call in both directions and check sound and video. If registration or media fails, ask the administrator to check the endpoint addresses, certificates, clock and network access. No automatic switch to an unencrypted connection is made.'
 ]
}
for filename, paragraphs in SECTIONS.items():
 path = ROOT/'docs'/filename
 doc = Document(path)
 removing = False
 for paragraph in list(doc.paragraphs):
  if paragraph.text == paragraphs[0]:
   removing = True
  if removing:
   paragraph._element.getparent().remove(paragraph._element)
 heading = doc.add_paragraph(paragraphs[0], style='Heading 1')
 heading.paragraph_format.page_break_before = True
 for text in paragraphs[1:]:
  doc.add_paragraph(text)
 doc.save(path)
