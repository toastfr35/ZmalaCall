"""Maintain release download instructions and the two phone Word authoring sources."""
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
RELEASES = 'https://github.com/toastfr35/ZmalaCall/releases/latest'
PHONE = {'phone_installation.docx': ('Install ZmalaPhone',
                             'For the person using an Android phone. You need the app download and your private '
                             'setup QR from the administrator. You do not need access to server administration.',
                             [('Before you start',
                               ['Use Android 9 or newer on a supported 64-bit phone. Have internet access and '
                                'your private App account setup QR. You can scan a printed code or one shown on '
                                'another screen, or open a QR picture saved from your email on the same phone.',
                                'Each account belongs to one phone or one Pi terminal. An App QR cannot enroll a '
                                'terminal, and a Terminal QR cannot enroll ZmalaPhone. Ask the person who '
                                'supplied your QR for a current App code if setup rejects it.']),
                              ('1. Download and install',
                               ['Use Download ZmalaPhone.apk on your private setup PDF, or open the release link '
                                'supplied by your administrator. The project release page is '
                                'https://github.com/toastfr35/ZmalaCall/releases/latest. The two ZmalaPhone PDF '
                                'files are the installation instructions and user guide.',
                                'Open the APK from Downloads or your file manager. If Android asks, allow that '
                                'browser or file manager to install apps, then return to the APK and tap Install. '
                                'You can turn off that permission after installation. No USB cable or SIM card is '
                                'needed for this installation method.',
                                'For an update from an earlier signed release, install the new APK over the '
                                'existing app. Your account setup stays in place. Do not uninstall just to '
                                'perform an ordinary update. Once the contact screen has an Updates control, use '
                                'it for later updates; see ZmalaPhone-Guide.pdf for optional automatic updates.',
                                'An earlier development/debug copy uses a different signing certificate. Android '
                                'cannot replace it with the release APK. Obtain your setup QR first, uninstall '
                                'the development copy, install the release and scan the QR again. Uninstalling '
                                "removes this phone's local setup; the server account and groups remain."]),
                              ('2. Connect your account',
                               ['Open ZmalaPhone. Choose Scan setup QR to use the camera, or Open QR image to '
                                'select a saved QR picture through Android. Choosing a picture does not upload '
                                'it. Cancel leaves setup unchanged.',
                                'Check the server address and tap Connect. Allow camera and microphone access for '
                                'video calls, and local network access on Android 17. You do not need access to '
                                'server administration. HTTP local setup warns that it is unencrypted; use it '
                                'only on a trusted home network.',
                                'Contacts appear after the account connects. The app follows your phone language '
                                'in English or French; Android may also offer an app-specific language setting. '
                                'To replace setup later, use Android Settings > Apps > ZmalaPhone > Storage > '
                                'Clear storage, then use a fresh App QR. Do not clear data for an ordinary '
                                'temporary connection problem.']),
                              ('3. Enable incoming calls',
                               ['Read the incoming-call explanation, tap Continue and allow notifications. The '
                                'contact footer reports enabled alerts, disabled notifications, registration '
                                'progress or unavailable alerts.',
                                'If notifications are off, tap Enable notifications to open the relevant Android '
                                'settings. Unavailable registration offers Try again; Details explains missing '
                                'server support. The person who supplied your QR can help. Internet access and a '
                                'configured server sender are needed for alerts while the app is closed.',
                                'After Android Force stop, open the app again before expecting calls. Open it at '
                                'least monthly to renew incoming alerts. Phone battery policies can affect '
                                'delivery; check the actual phone before relying on it.']),
                              ('4. Check a call before handover',
                               ['Tap a contact card to open that person’s page, then tap Call. Green Available '
                                'means recently active; blue Try calling means push may work but is unconfirmed. '
                                'Red Offline cards still open, with Call disabled and callback actions available '
                                'where supported.',
                                'Check moving video and speech in both directions. Rotate the phone and switch '
                                'cameras twice. Return to Home during an answered call and verify audio '
                                'continues; return through the ongoing notification and check video resumes. End '
                                'the call from the screen or notification.',
                                'Ask the other person to call once with ZmalaPhone open and once from the Home '
                                'screen or with the phone asleep. See ZmalaPhone-Guide.pdf for controls, '
                                'callbacks and everyday help.'])]),
 'phone_guide.docx': ('Use ZmalaPhone',
                      'For everyday video calls after your phone has been set up. If the welcome screen still '
                      'asks for a setup QR, follow ZmalaPhone-Installation.pdf first.',
                      [('Choose someone to call',
                        ['The contact list stays in portrait. Each person has one tappable card with a rounded '
                         'photo, name, availability and any call notices. Tap the card to open that person’s '
                         'page. Tap Call there to start the call; opening a card alone never calls.',
                         'Green Available means recently active. Blue Try calling means push may reach the phone, '
                         'but this is unconfirmed. Red Offline cards can still open for callbacks, while their '
                         'Call button is disabled. Long names and notices wrap; short lists are centred and '
                         'longer lists scroll.',
                         'The person’s page offers Call, Request callback or Cancel request, and Clear missed '
                         'calls where needed. Contacts or Android Back returns to the list. The app uses your '
                         'phone’s English or French language and supports larger Android text settings.']),
                       ('Missed calls and callbacks',
                        ['Readable notices distinguish Please call back (someone wants you to call them), '
                         'Callback requested (your request is pending), and missed-call counts. Both directions '
                         'can appear together. They stay visible beside that person’s name and on their page.',
                         'Open an offline contact’s page and choose Request callback to ask them to call you '
                         'later. The same action changes to Cancel request after server confirmation. Cancelling '
                         'removes only your pending request. A failed action keeps its last confirmed state and '
                         'can be retried.',
                         'After an unanswered, declined or cancelled outgoing call, the app also offers to '
                         'request a callback. Clear missed calls removes that person’s local count; a connected '
                         'call clears it too. Callback features require support on the server.']),
                       ('Receive calls',
                        ['An incoming call shows the caller’s portrait and name with separate Answer video call '
                         'and Decline actions. While the app is closed or the phone sleeps, Android shows an '
                         'incoming-call notification when alerts are available. Answer or Video reconnects and '
                         'answers that specific authorized call.',
                         'Once answered, Home, switching apps or locking the screen keeps audio running. Camera '
                         'sending pauses while the screen is hidden and resumes when you return. The ongoing call '
                         'notification lets you return or end the call. Android Force stop or stopping the call '
                         'service ends it; reopen the app afterward for incoming alerts.']),
                       ('During a call',
                        ['The large picture shows the other person; your small preview is at bottom right. Rotate '
                         'for portrait or landscape. Tap the video to reveal four round buttons with short '
                         'labels. They normally hide after five seconds; accessibility settings or keyboard focus '
                         'can keep them visible longer. The first call briefly explains tap and volume gestures.',
                         'Mic mutes or restores what the other person hears. A slash and a persistent Microphone '
                         'muted notice indicate mute. Sound cycles loudspeaker, earpiece and muted received '
                         'sound, skipping an unavailable earpiece. A persistent Sound muted notice distinguishes '
                         'this from microphone mute.',
                         'Swipe upward on video to raise listening volume, or downward to lower it. A percentage '
                         'appears briefly. Hardware volume buttons also adjust call volume. New calls use '
                         'loudspeaker at the existing Android call volume; raise it during the call if necessary.',
                         'Camera switches between front and rear cameras. Your preview preserves proportions and '
                         'follows rotation. End hangs up. Ringing pulses before answer. After answer, Connecting '
                         'video is shown for up to fifteen seconds; if video is late, a calm message replaces the '
                         'spinner without ending the call.']),
                       ('When something is not working',
                        ['A reconnecting notice means the server is temporarily unreachable. Check the network '
                         'and allow time to reconnect. An established call stays connected during a temporary '
                         'configuration outage; revoked account access still stops it. Ask the person who '
                         'supplied your QR for help with account or group problems.',
                         'If incoming alerts are unavailable, use the contact footer’s Enable notifications, Try '
                         'again or Details action. Check internet access and reopen after a deliberate Force '
                         'stop. Physical phone battery policies and locked-screen behavior should be checked '
                         'before handover.',
                         'For missing sound or video, check permissions, microphone mute, listening mute/volume '
                         'and the camera lens. Delayed video can still arrive. If it does not, end the call and '
                         'retry, noting the direction and whether sound worked. Calls across different networks '
                         'need the server’s secure relay configuration and an HTTPS setup QR.']),
                       ('Updates',
                        ['The installed version appears discreetly only at the bottom of the contact list. '
                         'Updates changes to Update available when a newer release is found, without opening a '
                         'dialog over your contacts. Tap it to view details and choose Update or Later. Later '
                         'defers prompting and automatic work for a day.',
                         'A selected update shows download percentage followed by Checking update, Preparing '
                         'installation and Installing update. Allow installation from ZmalaPhone if Android '
                         'requests it. Android may need confirmation. Updates keep setup; do not uninstall for an '
                         'ordinary update.',
                         'On Android 12 or later, optional Automatic updates on Wi-Fi starts off. It requires '
                         'installation permission, an unmetered connection and thirty seconds of visible idle '
                         'time. Touching the app restarts the idle timer; a person’s action page and all '
                         'ringing/connected calls postpone installation.',
                         'Downloads pause when a call starts or the app backgrounds. Reopen Updates to continue. '
                         'Installation briefly makes new calls unavailable. Android 9–11 requires manual '
                         'confirmation. If the installed app has no Updates action, install one newer APK '
                         'manually first.'])])}


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


def build_phone(filenames=None):
    for filename, (title, intro, sections) in PHONE.items():
        if filenames is not None and filename not in filenames:
            continue
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
            if heading in ('3. Enable incoming call alerts', 'Updates'):
                paragraph.paragraph_format.page_break_before = True
            for text in paragraphs:
                paragraph = doc.add_paragraph()
                paragraph.paragraph_format.keep_together = True
                before, found, after = text.partition(RELEASES)
                paragraph.add_run(before)
                if found:
                    # Preserve a real link in Word and the derived release PDF.
                    link = OxmlElement('w:hyperlink')
                    link.set(qn('r:id'), paragraph.part.relate_to(
                        RELEASES, RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
                    run = OxmlElement('w:r')
                    value = OxmlElement('w:t')
                    value.text = found
                    run.append(value)
                    link.append(run)
                    paragraph._p.append(link)
                    paragraph.add_run(after)
        footer = section.footer.paragraphs[0]
        footer.add_run('ZmalaPhone  |  ')
        field = OxmlElement('w:fldSimple')
        field.set(qn('w:instr'), 'PAGE')
        footer._p.append(field)
        doc.core_properties.title = title
        doc.core_properties.author = 'ZmalaCall'
        doc.core_properties.last_modified_by = ''
        doc.save(ROOT / 'docs' / filename)


def update_c20_guide():
    """Keep the retained terminal guide aligned with fixed Pi hardware."""
    path = ROOT / 'docs/terminal_config.docx'
    doc = Document(path)
    for paragraph in doc.paragraphs:
        if paragraph.text.startswith('The terminal serial is shown at the bottom of Settings.'):
            paragraph.text = (
                'The terminal serial is shown at the bottom of Settings. The Nuroum C20 '
                'automatically supplies the camera, microphone and speaker; there are no '
                'other device choices. If it is still waking, the terminal retries once '
                'per second and waits before connecting the call. You can still press red '
                'to cancel. Sound never switches to the TV. The server offers video '
                'resolution, frame rate, audio processing and C20 volume. Fresh video '
                'settings are 720p at 15 fps; media changes may wait until the call ends.')
        elif paragraph.text.startswith('From the contact carousel, hold red for '):
            paragraph.text = paragraph.text.replace('ten seconds', 'seven seconds', 1)
        elif paragraph.text.startswith(('Use left and right to select a setting.', 'Use left/right to choose a setting;')):
            paragraph.text = (
                'Use left/right to choose a setting; green opens it. Inside, left/right changes '
                'the draft, green saves and red discards it. Red on the list asks to exit: '
                'green confirms; red stays. Saved changes go to the server. If saving fails, '
                'retry after restoring the connection.')
    for row in doc.tables[0].rows:
        if row.cells[0].text == 'Speaker volume':
            paragraph = row.cells[1].paragraphs[0]
            paragraph.text = '0–100%, in steps of 5%'
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.05
            for run in paragraph.runs:
                run.font.size = Pt(11.5)
                run.bold = False
    doc.core_properties.author = 'ZmalaCall'
    doc.core_properties.last_modified_by = ''
    doc.save(path)


def update_qr_guides():
    """Describe the Pi scanner's positioning guides in the retained setup guide."""
    path = ROOT / 'docs/terminal_config.docx'
    doc = Document(path)
    for paragraph in doc.paragraphs:
        if paragraph.text.startswith('Hold the Wi-Fi QR steadily in front of the C20,'):
            paragraph.text = ('Hold the Wi-Fi QR steadily in front of the C20, with the whole '
                'code inside the four corner guides shown on the TV. Move the code closer '
                'or farther away until it fits clearly. Wait for success and the ten-second '
                'confirmation. When the server QR screen appears, show the server QR '
                'inside the same guides. An incorrect or unreachable server leaves an '
                'error and lets you try again.')
    doc.save(path)


def update_ringtone_guides():
    """Describe private ringtone choices and bounded previews in retained guides."""
    path = ROOT / 'docs/terminal_config.docx'
    doc = Document(path)
    table = doc.tables[0]
    if not any(row.cells[0].text == 'Ringtone' for row in table.rows):
        row = table.add_row()
        row.cells[0].text = 'Ringtone'
        row.cells[1].text = 'Nokia (default) and the sounds added on your server'
        speaker = next(row for row in table.rows if row.cells[0].text == 'Speaker volume')
        speaker._tr.addnext(row._tr)
    text = ('To choose a ringtone, open Ringtone in Settings with green. Use left and right '
            'to browse and hear each choice through the C20; the list wraps at both ends. A preview '
            'plays for up to ten seconds after a short pause. A waking C20 may take a moment. '
            'At zero volume the preview is silent. Press green to save, or red to cancel. '
            'An incoming call stops the preview. Nokia remains available if a new sound '
            'has not downloaded yet. The administrator can add sounds on the server.')
    existing = next((p for p in doc.paragraphs if p.text.startswith('To choose a ringtone,')), None)
    if existing is None:
        anchor = next(p for p in doc.paragraphs if p.text.startswith('The terminal serial is shown'))
        existing = doc.add_paragraph()
        anchor._p.addnext(existing._p)
    existing.text = text
    doc.save(path)
    path = ROOT / 'docs/server_prep.docx'
    doc = Document(path)
    text = ('To add ringtone choices, open Ringtone in Terminals. Preview plays on your '
            'computer. Add ringtones accepts audio you have permission to use '
            '(12 MB each, first 30 seconds). Choose a tone and Save changes. '
            'Nokia is the default; the private library is included in backups.')
    existing = next((p for p in doc.paragraphs if p.text.startswith('To add ringtone choices,')), None)
    if existing is None:
        anchor = next(p for p in doc.paragraphs if p.text.startswith('In Terminals, choose each'))
        existing = doc.add_paragraph()
        anchor._p.addnext(existing._p)
    existing.text = text
    existing.paragraph_format.space_after = Pt(0)
    for p in doc.paragraphs:
        if p.text.startswith('Use the server overview to keep a private copy'):
            p.text = ('Use the server overview to keep a private copy of your accounts, '
                      'settings, pictures and private ringtones. A backup also includes groups, '
                      'terminal identities, passwords, callback records and console history. '
                      'It does not contain Linux, Wi-Fi, SSH or TLS configuration.')
        if p.text == 'Back up and restore the server':
            previous = p._p.getprevious()
            if previous is not None and previous.xpath('.//w:br[@w:type="page"]'):
                previous.getparent().remove(previous)
                p.paragraph_format.page_break_before = True
    doc.save(path)


def update_presence_guides():
    """Keep the retained terminal instructions aligned with three-state presence."""
    for filename in ('terminal_use.docx', 'terminal_config.docx'):
        path = ROOT / 'docs' / filename
        doc = Document(path)
        for paragraph in doc.paragraphs:
            if filename == 'terminal_use.docx':
                paragraph.paragraph_format.page_break_before = False
            if paragraph.text.startswith('Choose a person with the arrow buttons,'):
                paragraph.text = ('Choose a person with the arrow buttons, press green to call and '
                    'press red to finish. Green Available means recently active; blue Try calling '
                    'means push may reach the phone, but this is unconfirmed. Either can be called. '
                    'Red Offline means no current connection or usable push registration. '
                    'This guide covers everyday calls with the Presenter remote after setup.')
            if paragraph.text.startswith('Contacts appear as compact rows with rounded photos'):
                paragraph.text = ('Contacts appear as compact rows with rounded photos beside their names. '
                    'Green Available means recently active. Blue Try calling means push may work, '
                    'but availability is unconfirmed. Tap a card to open that person’s page, then choose Call. Red Offline cards '
                    'still open for callback actions with Call disabled. Check sound, moving video, mute, camera switching and '
                    'hangup in both directions before relying on the phone. The Pi remote workflow is unchanged.')
            if paragraph.text == 'Point the C20 at the seating area. Call another permitted, online contact.':
                paragraph.text = 'Point the C20 at the seating area. Call a permitted green Available or blue Try calling contact.'
        doc.core_properties.author = 'ZmalaCall'
        doc.core_properties.last_modified_by = ''
        doc.save(path)



def update_terminal_volume_guides():
    """Use the same five-percent volume grid across terminal-facing controls."""
    for filename in ('terminal_use.docx', 'server_prep.docx'):
        path = ROOT / 'docs' / filename
        doc = Document(path)
        for paragraph in doc.paragraphs:
            if paragraph.text.startswith(('Hold the middle button. Move the remote gently up', 'Press the middle button to open the volume page')):
                paragraph.text = ('Press the middle button to open the volume page. '
                    'Click left for quieter sound or right for louder sound, in 5% steps. '
                    'The horizontal bar shows the volume. Press middle again to return. '
                    'During a call, the control appears over the video so you can keep seeing the other person. '
                    'Calls continue while adjusting volume; moving the remote has no effect.')
            elif paragraph.text.startswith(('The movement is relative:', 'The volume page changes')):
                paragraph.text = ('The volume page changes the sound you hear, not microphone volume. '
                    'It stays open until you press middle again. Incoming calls close it automatically. '
                    'For a saved starting volume, change Speaker volume in Settings.')
            elif paragraph.text.startswith(('If a person is offline, select them and press green.', 'Select an offline contact, press green and confirm')):
                paragraph.text = ('Select an offline contact, press green and confirm to request a callback. '
                    'A return-arrow badge marks your request. After an unanswered, declined or cancelled '
                    'outgoing call, Zmala asks: green requests a callback; red returns home. Incoming '
                    'requests show a large yellow Please call back flag over the requester’s picture '
                    'until completed or cancelled. Nothing dials automatically.')
            elif filename == 'server_prep.docx' and paragraph.text.startswith(('If checks or installation fail,', 'Read installation errors and keep the log')):
                paragraph.text = ('Read installation errors and keep the log in LocalAppData/ZmalaCall/ServerInstaller. '
                    'After a dropped connection, check whether installation is still running before retrying. '
                    'Back up server data regularly.')
            elif paragraph.text.startswith(("In Terminals, choose each terminal's language and settings", "In Terminals, save language and settings")):
                paragraph.text = ("In Terminals, save language and settings (volume: 5% steps, rounding existing values). "
                    'Open Setup for the Wi-Fi/server QR PDFs, then follow ZmalaTerminal-Guide.pdf. '
                    'The terminal card shows remote connection, battery/charger and C20 connection/power. '
                    'Reports become unavailable when the terminal stops reporting.')
        if filename == 'terminal_use.docx':
            from copy import deepcopy
            for table in doc.tables:
                for row in table.rows:
                    if row.cells[0].text == 'Middle long button':
                        paragraph = row.cells[1].paragraphs[0]
                        properties = deepcopy(paragraph.runs[0]._r.rPr) if paragraph.runs else None
                        paragraph.text = 'Open/close volume; left/right changes it in 5% steps'
                        if properties is not None:
                            paragraph.runs[0]._r.insert(0, properties)
        doc.save(path)

def update_terminal_feedback_guides():
    """Separate sound categories and retain the current page under volume controls."""
    for filename in ('terminal_use.docx', 'terminal_config.docx', 'server_prep.docx'):
        path = ROOT / 'docs' / filename
        doc = Document(path)
        for paragraph in doc.paragraphs:
            text = paragraph.text
            if text.startswith('Webcam icon (if shown):'):
                paragraph.style = 'Normal'
            if text.startswith(('Press the middle button to open the volume page',
                                'Press the middle button to show the call-volume overlay')):
                paragraph.text = ('Press the middle button to show the call-volume overlay. '
                    'Click left for quieter received call sound or right for louder sound, in 5% steps. '
                    'The horizontal bar and percentage sit in a black frame over the current page, '
                    'including during calls. Most of the page or video stays visible. '
                    'Press middle again to close it; moving the remote has no effect.')
            elif text.startswith(('The volume page changes', 'The call-volume overlay changes')):
                paragraph.text = ('The call-volume overlay changes only the sound you receive in a call. '
                    'Microphone gain stays unchanged. Ringtone volume and Button sounds volume are '
                    'separate Settings choices, each in 5% steps; 0% silences that category. '
                    'During idle navigation and Settings, left/right and middle play a short low tap, '
                    'green a rising tone and red a low double tap. '
                    'It is silent during calls, ringing and ringtone previews. '
                    'Incoming calls close the overlay automatically.')
            elif text.startswith('To choose a ringtone, open Ringtone'):
                paragraph.text = ('To choose a ringtone, open Ringtone in Settings with green. '
                    'Left/right browses the list, wrapping at either end, and previews through the C20 '
                    'at Ringtone volume after a short pause, for up to ten seconds. '
                    'Ringtone volume can be adjusted separately with the same preview. '
                    'Green saves after server confirmation; red cancels. A waking C20 may take a moment. '
                    'A call or leaving the editor stops the preview. Nokia remains available offline.')
            elif text.startswith(('In Terminals, save language and settings',
                                  'In Terminals, choose native-language labels')):
                paragraph.text = ('In Terminals, choose native-language labels from the same alphabetically '
                    'ordered 16-language list as the terminal. Set independent Call volume, Ringtone volume '
                    'and Button sounds volume in 5% steps. Open Setup for the Wi-Fi/server QR PDFs and '
                    'follow ZmalaTerminal-Guide.pdf. Device cards report remote battery/charger and C20 '
                    'connection/power; stale reports become unavailable.')
            elif text.startswith('Setup starts in English.'):
                paragraph.text = ('Setup starts in English. After enrollment, Language in Settings offers '
                    '16 native-language labels in alphabetic order, wrapping at both ends. '
                    'The same list is on the server. An older unsupported choice falls back to English '
                    'on upgrade. Detailed help may use English fallback.')
        for table in doc.tables:
            for row in table.rows:
                if row.cells[0].text == 'Middle long button':
                    row.cells[1].text = 'Open/close call-volume overlay; left/right changes it in 5% steps'
                elif row.cells[0].text in ('Speaker volume', 'Ringtone volume'):
                    row.cells[0].text = 'Ringtone volume'
                    row.cells[1].text = '0-100%, in 5% steps; separate from call volume'
                    if not any(r.cells[0].text == 'Button sounds volume' for r in table.rows):
                        added = deepcopy(row._tr)
                        row._tr.addnext(added)
                        for updated in table.rows:
                            if updated._tr is added:
                                updated.cells[0].text = 'Button sounds volume'
                                updated.cells[1].text = '0-100%, in 5% steps; quiet during calls and ringing'
        doc.save(path)


def update_callback_notification_guides():
    """Explain incoming callback alerts alongside the existing account and call flows."""
    for filename in ('phone_installation.docx', 'phone_guide.docx', 'terminal_config.docx', 'server_prep.docx'):
        path = ROOT / 'docs' / filename
        doc = Document(path)
        for paragraph in doc.paragraphs:
            text = paragraph.text
            if text.startswith(('Readable notices distinguish', 'Please call back marks an incoming request')):
                paragraph.text = ('Please call back marks an incoming request; Callback requested marks one you sent. '
                    'Both may appear with missed-call counts. An incoming request also creates an Android '
                    'notification naming the requester. Tap it to open their contact without calling. '
                    'Requests do not repeatedly alert; cancellation, a completed call or expiry removes '
                    'the alert. Manage Callback requests separately in Android notification settings.')
            elif text.startswith('Read the incoming-call explanation'):
                paragraph.text = text.replace('Read the incoming-call explanation', 'Read the call and callback notification explanation', 1)
            elif text.startswith('Allow notifications for incoming calls while'):
                paragraph.text = text.replace('Allow notifications for incoming calls while',
                    'Allow notifications for incoming calls and callback requests while', 1) + (
                    ' Callback alerts name the requester; tapping opens their contact without dialing.')
        doc.save(path)


def update_animated_portrait_guides():
    """Explain generic portrait uploads and selected-card playback in retained guides."""
    additions = {
        'server_prep.docx': ('In Accounts, create a Terminal account',
            'For an account portrait, choose PNG/JPG (up to 2 MiB, 8192 pixels per side and '
            '16 megapixels; square 480 × 480 recommended), or an animated GIF. GIFs must '
            'be square, 480 × 480 to 1024 × 1024 pixels, up to 16 MiB, 2–72 frames and '
            '5 seconds, with frame delays of 20–2000 ms. The account editor checks dimensions '
            'and shows an error if the picture does not fit. The server checks it again. '
            'GIFs play once when selected on a terminal, then stay still; phones show a still picture.'),
        'terminal_use.docx': ('Press left or right until their portrait',
            'If your helper supplied an animated portrait, it plays once when you select '
            'that person, then stays still. Move away and back to see it again. '
            'Animation stops when you navigate or start a call.')}
    for filename, (anchor_text, text) in additions.items():
        path = ROOT / 'docs' / filename
        doc = Document(path)
        existing = next((p for p in doc.paragraphs if p.text.startswith(text[:45])), None)
        if existing is None:
            anchor = next(p for p in doc.paragraphs if p.text.startswith(anchor_text))
            existing = doc.add_paragraph()
            anchor._p.addnext(existing._p)
        existing.text = text
        existing.paragraph_format.space_after = Pt(6)
        doc.save(path)


if __name__ == '__main__':
    update_existing()
    update_c20_guide()
    update_qr_guides()
    update_ringtone_guides()
    update_terminal_volume_guides()
    build_phone()
    update_presence_guides()
    update_terminal_feedback_guides()
    update_callback_notification_guides()

    update_animated_portrait_guides()
