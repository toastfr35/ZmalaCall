"""Update retained operator guides for App/Terminal enrollment (document workspace runtime)."""
from pathlib import Path
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
TITLE = 'Setting up ZmalaPhone'
SECTIONS = {
    'server_prep.docx': [
        'ZmalaPhone is the Android companion. It supports local calls or encrypted calls across different networks when the server is configured for remote access, plus Firebase incoming alerts while closed.',
        'As administrator, create an App account in Accounts and add it to a calling group. Download its server QR PDF from connection details and give it to the phone user by email or on paper. The phone user does not need server admin access.',
        'Download the signed ZmalaPhone APK from the release link supplied by the administrator. Open it and allow installation from your browser or file manager when Android asks. Install, choose Scan setup QR and allow camera and microphone access. On Android 17, also allow local network access. Scan the supplied QR from paper or another screen and confirm the server address. Later signed releases install as updates and keep setup. A development/debug copy must first be removed; obtain a fresh setup QR before replacing it.',
        'Allow notifications to receive incoming calls while using another app or when the phone sleeps. Both phone and server need internet for alerts. Remote calls use the public server address; local-only deployments need the same reachable local network. If Android Force stop is used, open ZmalaPhone again. Reopen it after changing notification settings, and at least monthly to renew alerts. The Pi needs its private Firebase sender configuration; contact the administrator if alerts are unavailable.',
        'Each account is either App or Terminal, never both. A phone cannot scan a Terminal QR. Changing an account type replaces its enrollment and SIP credentials; the previous device loses access. Give the new device a fresh QR code. Use separate accounts for a phone and a Pi terminal.',
        'When enabling remote access, use a stable public hostname, trusted certificates and the server relay configuration described in docs/server.md. Reserve the Pi address and forward only the listed server ports. Provide fresh HTTPS setup QR codes to existing devices. Keep the QR page private because it grants access to the account. To remove phone setup, use Android Settings > Apps > ZmalaPhone > Storage > Clear storage (Clear app data on some phones). There is no reset button in the app. Re-enrollment uses an App QR from the administrator. The existing account and group memberships remain on the server.',
        'During a call, tap the video to show four round controls; they hide after five seconds without interaction. The microphone button mutes or restores what the other person hears; a slash means it is muted. The separate listening button cycles loudspeaker (sound waves), earpiece (phone icon) and muted call sound (crossed speaker), skipping an unavailable earpiece. Listening mute does not mute your microphone. Swipe up on the video to raise listening volume, or down to lower it; a percentage appears briefly. The phone volume buttons also adjust call volume. New calls start on loudspeaker at the existing Android call volume. Switch camera changes between the front and rear cameras; red hangup ends the call. Your preview keeps the camera picture proportions at bottom right, above the controls when visible, and follows portrait or landscape rotation. A pulsing phone shows outgoing ringing. After answer, Connecting video and a spinner remain until the first remote video frame arrives.',
        'Contacts appear as compact rows with rounded photos beside their names. Green Available means recently active; blue Try calling means push may reach the phone, but this is unconfirmed. Tap either name to try a call. Red Offline means no current connection or usable push registration and cannot start a call. Before handover, test calls in both directions, moving video, speech, mute, camera switching, decline and hangup. Keep ZmalaPhone open during an answered call; leaving it ends media. Registration alone does not prove call quality.'
    ],
    'terminal_config.docx': [
        'A Pi terminal requires a Terminal account. ZmalaPhone requires a separate App account. Add the two accounts to a shared calling group so they can call each other.',
        'Ask the administrator for the signed ZmalaPhone APK download link and your account setup QR. Open the downloaded APK, allow installation from your browser or file manager when Android asks, and install. You do not need server admin access. Open ZmalaPhone, choose Scan setup QR, allow camera and microphone access and scan the code from paper or another screen. On Android 17, also allow local network access. Confirm the displayed server address. Later signed releases keep setup when installed as updates. Replacing a development/debug copy requires uninstalling it first and obtaining a fresh setup QR.',
        'Allow notifications to receive calls while ZmalaPhone is closed or the phone sleeps. Internet is needed for alerts. Calls can cross different networks when the administrator enables encrypted remote access and supplies an HTTPS setup QR. If Android Force stop is used, reopen ZmalaPhone. Enable disabled notifications in Android Settings and reopen it; also reopen at least monthly to renew alerts.',
        'Do not change the Pi account to App to add a phone. A type change revokes the old enrollment and SIP password; it replaces the device instead of adding another one. If a type change is intentional, print a fresh QR and repeat setup on the replacement device.',
        'The Android preview uses the same logo and colours as the terminal. It supports local or encrypted remote video calls and Firebase incoming alerts while closed. For remote calls, both devices use HTTPS setup and the configured encrypted server relay; their routers need no inbound forwarding rules.',
        'During a call, tap the video to show four round controls; they hide after five seconds without interaction. The microphone button mutes or restores what the other person hears; a slash means it is muted. The separate listening button cycles loudspeaker (sound waves), earpiece (phone icon) and muted call sound (crossed speaker), skipping an unavailable earpiece. Listening mute does not mute your microphone. Swipe up on the video to raise listening volume, or down to lower it; a percentage appears briefly. The phone volume buttons also adjust call volume. New calls start on loudspeaker at the existing Android call volume. Switch camera changes between the front and rear cameras; red hangup ends the call. Your preview keeps the camera picture proportions at bottom right, above the controls when visible, and follows portrait or landscape rotation. A pulsing phone shows outgoing ringing. After answer, Connecting video and a spinner remain until the first remote video frame arrives.',
        'To remove phone setup, use Android Settings > Apps > ZmalaPhone > Storage > Clear storage (Clear app data on some phones), then scan an App QR again. This leaves the server account unchanged.',
        'Contacts appear as compact rows with rounded photos beside their names. Green Available means recently active; blue Try calling means push may reach the phone, but this is unconfirmed. Tap either name to try a call. Red Offline means no current connection or usable push registration and cannot start a call. Check a call in each direction, sound, moving video, mute, camera switching and hangup before relying on the phone. The Pi remote-control workflow is unchanged.'
    ]
}

def update():
    for filename, paragraphs in SECTIONS.items():
        path = ROOT / 'docs' / filename
        doc = Document(path)
        removing = False
        for paragraph in list(doc.paragraphs):
            if paragraph.text == TITLE:
                removing = True
            elif removing and paragraph.style.name == 'Heading 1':
                removing = False
            if removing:
                paragraph._element.getparent().remove(paragraph._element)
            elif paragraph.text.startswith('In Accounts, create an account for each terminal or phone,'):
                paragraph.text = 'In Accounts, create a Terminal account for each Pi terminal and an App account for each Android phone. Set its display name and portrait, keep generated credentials private and supply real email addresses where reminders are needed.'
        heading = doc.add_paragraph(TITLE, style='Heading 1')
        heading.paragraph_format.page_break_before = True
        for text in paragraphs:
            doc.add_paragraph(text)
        doc.save(path)

if __name__ == '__main__':
    update()
