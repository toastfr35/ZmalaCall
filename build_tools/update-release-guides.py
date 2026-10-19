"""Maintain release download instructions and the two phone Word authoring sources."""
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
RELEASES = 'https://github.com/toastfr35/ZmalaCall/releases/latest'
PHONE = {
    'phone_installation.docx': (
        'Install ZmalaPhone',
        'For the person using an Android phone. You need the app download and your private setup QR from the administrator. You do not need access to server administration.',
        [
            ('Before you start', [
                'Use Android 9 or newer on a supported 64-bit phone. Have a working internet connection and an App account setup QR. The QR may be printed or displayed on another screen; a QR saved on the same phone must first be shown elsewhere so the camera can scan it.',
                'Each account belongs to one phone or one Pi terminal. An App QR cannot enroll a terminal, and a Terminal QR cannot enroll ZmalaPhone. Ask the administrator for the correct account if setup rejects the code.',
            ]),
            ('1. Download and install', [
                'Open the release link supplied by your administrator and download ZmalaPhone.apk. The project release page is ' + RELEASES + '. The two ZmalaPhone PDF files are the installation instructions and user guide.',
                'Open the APK from Downloads or your file manager. If Android asks, allow that browser or file manager to install apps, then return to the APK and tap Install. You can turn off that permission after installation. No USB cable or SIM card is needed for this installation method.',
                'For an update from an earlier signed release, install the new APK over the existing app. Your account setup stays in place. Do not uninstall just to perform an ordinary update. Once the contact screen has an Updates control, use it for later updates; see ZmalaPhone-Guide.pdf for optional automatic updates.',
                'An earlier development/debug copy uses a different signing certificate. Android cannot replace it with the release APK. Obtain your setup QR first, uninstall the development copy, install the release and scan the QR again. Uninstalling removes this phone\'s local setup; the server account and groups remain.',
            ]),
            ('2. Scan your setup QR', [
                'Open ZmalaPhone and tap Scan setup QR. Allow camera and microphone access when requested. On Android versions that request local network access, allow it too. Hold the complete QR inside the camera view and confirm the expected server address.',
                'Keep your QR private: it grants access to your account. If it fails, ask the administrator for a current App QR. For calls between different networks, the administrator must first enable secure remote access and supply an HTTPS QR.',
            ]),
            ('3. Enable incoming call alerts', [
                'Read the incoming-call explanation, tap Continue and allow notifications when Android asks. Check that the app reports Incoming call alerts enabled. The phone and server need internet access for Firebase alerts, and the administrator must configure the sender.',
                'If alerts are disabled, enable ZmalaPhone notifications in Android Settings and reopen the app. Open it again after using Force stop, and at least monthly to renew alerts. Contact the administrator if alerts remain unavailable.',
            ]),
            ('4. Check a call before handover', [
                'Tap an online green contact and ask the other person to answer. Check moving video and speech in both directions, then hang up. Ask them to call you back once with ZmalaPhone open and once after returning to the phone Home screen.',
                'Rotate the phone and switch cameras twice during a call. Check that the picture stays upright and the front camera returns. See ZmalaPhone-Guide.pdf for the call controls and everyday help.',
            ]),
        ],
    ),
    'phone_guide.docx': (
        'Use ZmalaPhone',
        'For everyday video calls after your phone has been set up. If the welcome screen still asks for a setup QR, follow ZmalaPhone-Installation.pdf first.',
        [
            ('Choose someone to call', [
                'Contacts appear with a photo and name. A green name means the contact is online: tap it to call. A gray name means offline and cannot be tapped to start a call. Scroll when there are more contacts than fit on screen.',
                'A pulsing phone animation appears while the other end rings. After answer, Connecting video stays visible until the first remote video frame arrives. A brief wait can happen while the connection starts.',
            ]),
            ('Missed calls and callback requests', [
                'A red missed-call arrow and count on a contact portrait show calls you did not answer. A green return arrow means that person has asked you to call back; a green outgoing arrow means your request is pending. Tap the callback icon beside the name for details or to clear missed calls.',
                'For an offline contact, tap the callback icon and choose Request callback. After an unanswered outgoing call, the app also offers Request callback. This sends a request through the Zmala server; it does not place another call. Repeated requests remain one pending request for the pair.',
                'When the contact becomes available, tap their green name to call. A connected call completes pending callback requests between you and clears your missed-call count for that person. The administrator controls request expiry. If the action is absent, the server needs an update to support app callbacks.',
            ]),
            ('Answer an incoming call', [
                'Use Answer or Decline on the incoming-call screen or notification. Incoming alerts can arrive while you use another app or the phone sleeps when notifications and server push are configured. Unlock the phone if Android requires it.',
                'Keep ZmalaPhone visible during an answered video call. Leaving the app ends its call media. After a deliberate Android Force stop, open the app again before expecting incoming calls.',
            ]),
            ('Reset setup only when needed', [
                'To deliberately remove setup, use Android Settings > Apps > ZmalaPhone > Storage > Clear storage (sometimes Clear app data). This requires a setup QR again and does not delete the server account. Do not clear data as the first response to a temporary network problem.',
            ]),
            ('During a call', [
                'The large picture shows the other person; the small view at bottom right shows your own camera. Rotate your phone for portrait or landscape. Tap the video to show the four round controls; they disappear after five seconds without interaction.',
                'Microphone: mute or restore your microphone. Audio output: change where you hear the call. Switch camera: alternate the available front and rear cameras. Red hangup: end the call.',
                'Use the phone volume buttons to change listening volume. Camera switching changes your outgoing picture; it does not change the other person\'s camera.',
            ]),
            ('When something is not working', [
                'No contacts or everyone offline: check your network connection and wait for the app to reconnect. Ask the administrator to check account groups and server availability. A phone and terminal need separate accounts in a shared calling group.',
                'No incoming alerts: enable notifications in Android Settings and reopen ZmalaPhone. Check internet access and ask the administrator whether the Firebase sender is configured. Open the app at least monthly to renew alerts.',
                'No sound or video: check camera and microphone permissions, microphone mute, listening volume and the camera lens. If Connecting video does not clear, end the call and retry; report which direction failed and whether sound worked.',
                'Calls work only on one network: ask the administrator to check secure remote access and whether your setup QR uses the HTTPS server address. A local-only server cannot support calls across arbitrary networks.',
            ]),
            ('Updates', [
                'The installed version appears discreetly at the bottom of the contact screen, beside Updates. Tap Updates to check now. When a newer published version is available, choose Update or Later. Later postpones reminders and automatic updates for a day.',
                'Allow installation from ZmalaPhone when Android opens Settings, then return and tap Update. Android 9 to 11 requires confirmation. Updates preserve your setup. If your older app has no Updates button, install one APK manually first; see ZmalaPhone-Installation.pdf.',
                'On Android 12 or later, Automatic updates on Wi-Fi is optional and initially off. It requires installation permission, an unmetered connection and 30 seconds with the app open and idle. If Android still requires approval, tap Update to continue.',
                'Updates wait during calls. Downloads pause when a call starts or you leave the app; reopen Updates to continue. Calls are briefly unavailable during installation. Do not uninstall the app for ordinary updates.',
            ]),
        ],
    ),
}


def update_existing():
    replacements = {
        'terminal_prep.docx': 'ZmalaTerminal-Installation.pdf',
        'terminal_config.docx': 'ZmalaTerminal-Guide.pdf',
        'terminal_use.docx': 'ZmalaTerminal-Guide.pdf',
        'server_prep.docx': 'ZmalaServer-Installation.pdf',
    }
    for filename in ('terminal_prep.docx', 'terminal_config.docx', 'server_prep.docx'):
        path = ROOT / 'docs' / filename
        doc = Document(path)
        for p in doc.paragraphs:
            text = p.text
            for old, new in replacements.items():
                text = text.replace(old, new)
            if text.startswith('Open the newest successful Build terminal installer run'):
                text = ('Open the release link supplied by your administrator. Download '
                        'ZmalaTerminal-Pi4-setup.exe and the two ZmalaTerminal PDF guides. '
                        'Run the executable on your Windows PC; it installs the software on the Pi over Ethernet.')
            if text.startswith('Open the latest successful Build server installer run'):
                text = ('Open the release link supplied by your administrator. Download '
                        'ZmalaServer-Pi4-setup.exe and the two ZmalaServer PDF guides. '
                        'Run the executable on your Windows PC; the PDF guides sit beside it.')
            if text.startswith('A published release is another option'):
                text = ('Development builds are also available from successful GitHub Actions runs. '
                        'They may require GitHub sign-in and are separate from published releases.')
            if text != p.text:
                p.text = text
            # Replace old Actions download links without destroying hyperlink markup.
            for relation in list(p.part.rels.values()):
                if relation.is_external and '/actions/workflows/build-' in str(relation.target_ref):
                    relation._target = RELEASES
            for node in p._p.iter(qn('w:t')):
                if node.text and node.text.startswith('Latest successful '):
                    node.text = 'Published ZmalaCall releases'
        doc.core_properties.author = 'ZmalaCall'
        doc.core_properties.last_modified_by = ''
        doc.save(path)


def build_phone():
    for filename, (title, intro, sections) in PHONE.items():
        doc = Document()
        section = doc.sections[0]
        section.page_width, section.page_height = Inches(8.27), Inches(11.69)
        section.top_margin = section.bottom_margin = Inches(.7)
        section.left_margin = section.right_margin = Inches(.8)
        for name, size in [('Normal', 11), ('Title', 27), ('Heading 1', 16)]:
            style = doc.styles[name]
            style.font.name = 'Calibri'
            style.font.size = Pt(size)
            style.font.color.rgb = RGBColor.from_string('1F2937')
            style.paragraph_format.space_after = Pt(8)
            style.paragraph_format.line_spacing = 1.1
        for border in doc.styles.element.xpath('.//w:pBdr'):
            border.getparent().remove(border)
        doc.styles['Heading 1'].font.color.rgb = RGBColor.from_string('16734B')
        doc.styles['Heading 1'].paragraph_format.keep_with_next = True
        doc.add_paragraph(title, 'Title')
        doc.add_paragraph(intro)
        for heading, paragraphs in sections:
            paragraph = doc.add_heading(heading, 1)
            if heading in ('3. Enable incoming call alerts', 'During a call'):
                paragraph.paragraph_format.page_break_before = True
            for text in paragraphs:
                doc.add_paragraph(text)
        footer = section.footer.paragraphs[0]
        footer.add_run('ZmalaPhone  |  ')
        field = OxmlElement('w:fldSimple')
        field.set(qn('w:instr'), 'PAGE')
        footer._p.append(field)
        doc.core_properties.title = title
        doc.core_properties.author = 'ZmalaCall'
        doc.core_properties.last_modified_by = ''
        doc.save(ROOT / 'docs' / filename)


if __name__ == '__main__':
    update_existing()
    build_phone()
