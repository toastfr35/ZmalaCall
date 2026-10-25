"""Shared terminal translations; management UI and account names stay unchanged."""
import json
from pathlib import Path

LANGUAGES = json.loads((Path(__file__).resolve().parent / 'shared/terminal-languages.json').read_text(encoding='utf-8'))
SETUP = json.loads((Path(__file__).resolve().parent / 'shared/setup-translations.json').read_text(encoding='utf-8'))
for language, values in SETUP.items():
    LANGUAGES[language]['messages'].update(zip(['factory_reset', 'reset', 'keep_configuration'], values))
WIFI_CONFIRMATION = json.loads((Path(__file__).resolve().parent / 'shared/wifi-confirmation.json').read_text(encoding='utf-8'))
for language, values in WIFI_CONFIRMATION.items():
    LANGUAGES[language]['messages'].update(zip(['wifi_connected', 'server_qr_next'], values))
# @llr LLR-TERM-UI-023
VIDEO_MESSAGES = json.loads((Path(__file__).resolve().parent / 'shared/video-messages.json').read_text(encoding='utf-8'))
for language, values in VIDEO_MESSAGES.items():
    LANGUAGES[language]['messages'].update(zip(['no_remote_video', 'audio_continues', 'starting_video'], values))
CALL_QUESTIONS = json.loads((Path(__file__).resolve().parent / 'shared/call-questions.json').read_text(encoding='utf-8'))
for language, values in CALL_QUESTIONS.items():
    LANGUAGES[language]['messages'].update(zip(['call_question', 'callback_question', 'callback_requested'], values))
# @llr LLR-TERM-HISTORY-022
INCOMING_CALLBACK_MESSAGES = json.loads((Path(__file__).resolve().parent / 'shared/incoming-callback-messages.json').read_text(encoding='utf-8'))
for language, message in INCOMING_CALLBACK_MESSAGES.items():
    LANGUAGES[language]['messages']['callback_received'] = message
CONFIRMATION_PROMPTS = json.loads((Path(__file__).resolve().parent / 'shared/confirmation-prompts.json').read_text(encoding='utf-8'))
for language, values in CONFIRMATION_PROMPTS.items():
    LANGUAGES[language]['messages'].update(zip(['yes', 'no', 'contact_unavailable'], values))
REMOTE_MESSAGES = json.loads((Path(__file__).resolve().parent / 'shared/remote-messages.json').read_text(encoding='utf-8'))
REMOTE_ORIENTATION = json.loads((Path(__file__).resolve().parent / 'shared/remote-orientation.json').read_text(encoding='utf-8'))
REMOTE_ORIENTATION_KEYS = ('remote_picture_front', 'remote_picture_back', 'remote_picture_power',
                           'remote_disconnected_title', 'remote_disconnected_detail')
for language, values in REMOTE_ORIENTATION.items():
    REMOTE_MESSAGES.setdefault(language, {}).update(zip(REMOTE_ORIENTATION_KEYS, values))


# @llr LLR-TERM-NAV-005
PRESENCE_MESSAGES = {
    'en': {'available': 'Available', 'try_calling': 'Try calling'},
    'fr': {'available': 'Disponible', 'try_calling': 'Essayer d’appeler'},
}


# @llr LLR-TERM-UI-023
def translate(language, key, **values):
    # Picture labels and turn-over instructions cover every selectable language.
    # The more detailed Bluetooth diagnostic copy still has an English fallback.
    if key in PRESENCE_MESSAGES['en']:
        return PRESENCE_MESSAGES.get(language, PRESENCE_MESSAGES['en'])[key]
    if key in REMOTE_MESSAGES['en']:
        return REMOTE_MESSAGES.get(language, {}).get(key, REMOTE_MESSAGES['en'][key]).format(**values)
    messages = LANGUAGES.get(language, LANGUAGES['en'])['messages']
    return messages.get(key, LANGUAGES['en']['messages'][key]).format(**values)


def font_family(language, available):
    """Prefer Windows fonts for the selected script, with installed fallbacks."""
    if language in ('zh-Hans', 'zh-Hant', 'ja'):
        candidates = ['Microsoft YaHei UI', 'Microsoft JhengHei UI', 'Yu Gothic UI', 'Meiryo', 'SimSun']
        if language == 'ja':
            candidates = ['Yu Gothic UI', 'Meiryo', 'MS Gothic', *candidates]
        elif language == 'zh-Hant':
            candidates = ['Microsoft JhengHei UI', *candidates]
    elif language == 'ko':
        candidates = ['Malgun Gothic']
    elif language in ('hi', 'bn', 'pa', 'gu', 'mr', 'ta', 'te', 'kn', 'ml', 'or', 'as', 'ne', 'si'):
        candidates = ['Nirmala UI']
    elif language in ('th', 'lo', 'km'):
        candidates = ['Leelawadee UI']
    elif language == 'my':
        candidates = ['Myanmar Text', 'Nirmala UI']
    elif language in ('bo', 'dz'):
        candidates = ['Microsoft Himalaya']
    elif language == 'dv':
        candidates = ['MV Boli']
    else:
        candidates = []
    return next((name for name in [*candidates, 'Segoe UI', 'Noto Sans', 'DejaVu Sans', 'Arial'] if name in available), 'TkDefaultFont')
