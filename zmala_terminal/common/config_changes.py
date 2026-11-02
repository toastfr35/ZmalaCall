"""Pure decisions for applying a validated server snapshot.

The UI owns when to apply these decisions; this module never opens devices,
refreshes credentials, advances a revision or retains a pending configuration.
"""
from dataclasses import dataclass
from zmala_terminal.common.secure_calls import credentials_only


@dataclass(frozen=True)
class ConfigurationUpdate:
    language: str
    auto_framing: bool
    incoming_allowed: bool
    auto_answer_allowed: bool
    renew_credentials: bool


# @llr LLR-TERM-CONFIG-024, LLR-TERM-COM-010
def classify_update(previous, desired, caller=None):
    contact = next((c for c in desired['contacts'] if c['id'] == caller), None)
    return ConfigurationUpdate(
        language=desired.get('language', 'en'),
        auto_framing=desired.get('auto_framing', False),
        incoming_allowed=bool(contact and contact['can_receive']),
        auto_answer_allowed=bool(contact and desired.get('auto_answer', contact.get('auto_answer', False))),
        renew_credentials=credentials_only(previous, desired),
    )


@dataclass(frozen=True)
class MediaSnapshot:
    sip: dict | None
    secure_calls: dict | None
    resolution: str | None
    fps: int
    audio_profile: str

    # @llr LLR-TERM-CONFIG-023
    def needs_rebuild(self, desired, audio_profile):
        return (self.sip != desired['sip'] or self.secure_calls != desired.get('secure_calls')
            or ('video_resolution' in desired and self.resolution != desired['video_resolution'])
            or self.fps != desired.get('video_fps', 15) or self.audio_profile != audio_profile)

