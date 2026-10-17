"""Validate management responses before they influence SIP credentials, pictures or UI state."""
import re
from localization import LANGUAGES
from local_settings import TV_IDLE_DELAYS
from video_settings import FRAME_RATES


def validate(config, device_id):
    if not isinstance(config, dict):
        raise ValueError('Configuration must be an object')
    if config.get('schema_version') != 1 or config.get('device_id') != device_id:
        raise ValueError('Configuration schema or device identity mismatch')
    if type(config.get('configuration_version')) is not int or config['configuration_version'] < 1:
        raise ValueError('Invalid configuration version')
    if config.get('command_shell', 'powershell') not in ('powershell', 'pwsh', 'cmd', 'sh', 'bash'):
        raise ValueError('Unsupported command shell')
    if config.get('audio_profile', 'normal') not in ('normal', 'speech'):
        raise ValueError('Unsupported audio profile')
    if 'video_resolution' in config and config['video_resolution'] not in ('360p', '480p', '720p', '1080p'):
        raise ValueError('Unsupported video resolution')
    if 'video_fps' in config and (type(config['video_fps']) is not int or config['video_fps'] not in FRAME_RATES):
        raise ValueError('Unsupported video frame rate')
    if 'carousel_portraits' in config and (type(config['carousel_portraits']) is not int
                                          or config['carousel_portraits'] not in (3, 5)):
        raise ValueError('Choose 3 or 5 carousel portraits')
    if 'tv_idle_seconds' in config and (type(config['tv_idle_seconds']) is not int
                                        or config['tv_idle_seconds'] not in TV_IDLE_DELAYS):
        raise ValueError('Unsupported TV idle timeout')
    if 'auto_framing' in config and type(config['auto_framing']) is not bool:
        raise ValueError('Automatic framing must be enabled or disabled')
    if 'c20_speaker_volume' in config and (type(config['c20_speaker_volume']) is not int
                                         or not 0 <= config['c20_speaker_volume'] <= 100):
        raise ValueError('C20 speaker volume must be 0–100 percent')
    if not isinstance(config.get('display_name'), str) or len(config['display_name']) > 80:
        raise ValueError('Invalid display name')
    if not isinstance(config.get('language', 'en'), str) or config.get('language', 'en') not in LANGUAGES:
        raise ValueError('Unsupported terminal language')
    if type(config.get('auto_answer_seconds')) is not int or not 5 <= config['auto_answer_seconds'] <= 600:
        raise ValueError('Invalid auto-answer countdown')
    if 'auto_answer' in config and type(config['auto_answer']) is not bool:
        raise ValueError('Invalid account auto-answer setting')
    sip = config.get('sip', {})
    if not isinstance(sip, dict):
        raise ValueError('Invalid SIP account')
    if not isinstance(config.get('call_auth_key'), str) or len(config['call_auth_key']) < 20:
        raise ValueError('Missing server call authentication key')
    for key in ['username', 'password', 'domain', 'proxy']:
        if not isinstance(sip.get(key), str) or not sip[key]:
            raise ValueError('Invalid SIP account')
    validate_contacts(config.get('contacts'), sip)
    validate_callbacks(config.get('callbacks', []), sip['username'])
    return config


def validate_contacts(contacts, sip):
    if not isinstance(contacts, list) or len(contacts) > 40:
        raise ValueError('Invalid contacts')
    seen = set()
    for c in contacts:
        if not isinstance(c, dict):
            raise ValueError('Invalid contact')
        if not isinstance(c.get('id'), str) or c['id'] in seen or not re.fullmatch(r'[a-z][a-z0-9_-]{0,30}', c['id']):
            raise ValueError('Invalid contact identity')
        seen.add(c['id'])
        if not isinstance(c.get('name'), str) or not c['name'].strip() or len(c['name']) > 80:
            raise ValueError('Invalid contact name')
        if c.get('sip_uri') != f"sip:{c['id']}@{sip['domain']}":
            raise ValueError('Invalid contact address')
        for key in ['can_call', 'can_receive', 'auto_answer']:
            if type(c.get(key)) is not bool:
                raise ValueError('Invalid contact permission')
        if 'online' in c and type(c['online']) is not bool:
            raise ValueError('Invalid contact availability')
        if c['auto_answer'] and not c['can_receive']:
            raise ValueError('Invalid auto-answer permission')
        if c.get('photo') and not re.fullmatch(r'/photos/[a-f0-9]+\.(png|jpg)', c['photo']):
            raise ValueError('Invalid photo path')


def validate_callbacks(callbacks, username):
    if not isinstance(callbacks, list) or len(callbacks) > 80:
        raise ValueError('Invalid callback requests')
    for request in callbacks:
        if not isinstance(request, dict) or not isinstance(request.get('id'), str) or not re.fullmatch(r'[a-f0-9-]{36}', request['id']) or request.get('status') != 'pending' or type(request.get('ready')) is not bool:
            raise ValueError('Invalid callback request')
        if any(not isinstance(request.get(key), str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,30}', request[key]) for key in ['from', 'to']) or username not in (request['from'], request['to']):
            raise ValueError('Invalid callback account')
