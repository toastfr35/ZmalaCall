"""Settings drafts and the deliberate red-button hold; no native I/O."""
from zmala_terminal.common.localization import LANGUAGES

FIELDS = ('language', 'auto_answer', 'auto_framing', 'c20_speaker_volume', 'ringtone', 'carousel_portraits', 'tv_idle_seconds', 'reset')
TV_IDLE_DELAYS = (30, 60, 120, 300, 600, 1200, 0)
ANSWER_DELAYS = (0, 10, 30, 60, 120, 300, 600)


# @llr LLR-TERM-CONFIG-018
class SettingsHold:
    def __init__(self):
        self.clear()

    def clear(self):
        self.started = None
        self.progress = 0.0

    @property
    def capturing(self):
        return self.started is not None and self.progress >= .2

    def start(self, now):
        if self.started is None:
            self.started = now

    def update(self, now):
        if self.started is not None:
            self.progress = min(1.0, max(0.0, (now-self.started)/10))
            return self.progress >= 1
        return False


class SettingsDraft:
    def __init__(self):
        self.row = 0
        self.editing = False
        self.confirm_exit = False
        self.busy = False
        self.error = False
        self.options = []
        self.index = 0
        self.expected = {}

    @property
    def key(self):
        return FIELDS[self.row]

    @staticmethod
    def value(config, key):
        if key == 'auto_answer':
            return config.get('auto_answer_seconds', 10) if config.get(key) else 0
        return config.get(key, {'language': 'en', 'auto_framing': False,
                               'c20_speaker_volume': 50, 'ringtone': 'nokia', 'carousel_portraits': 3, 'tv_idle_seconds': 30}.get(key))

    # @llr LLR-TERM-CONFIG-021, LLR-TERM-AUDIO-009
    def open(self, config):
        if self.key == 'reset':
            raise ValueError('Reset uses its own confirmation page')
        self.editing, self.error = True, False
        key, value = self.key, self.value(config, self.key)
        self.options = (sorted(LANGUAGES, key=lambda code: LANGUAGES[code]['name']) if key == 'language'
                        else [item['id'] for item in config.get('ringtones', [{'id': 'nokia'}])] if key == 'ringtone'
                        else list(ANSWER_DELAYS) if key == 'auto_answer'
                        else list(TV_IDLE_DELAYS) if key == 'tv_idle_seconds'
                        else [False, True] if key == 'auto_framing'
                        else list(range(0, 101, 5)) if key == 'c20_speaker_volume' else [3, 5])
        self.index = self.options.index(value) if value in self.options else 0
        if key == 'c20_speaker_volume' and value not in self.options:
            self.index = min(range(len(self.options)), key=lambda i: abs(self.options[i]-value))
        if key == 'auto_answer' and value and value not in self.options:
            # Existing administrator values such as 5 or 90 seconds should
            # select the next supported delay, never silently select Never.
            self.index = next(i for i, option in enumerate(self.options) if option >= value)
        self.expected = self.fields(config, value)

    def fields(self, config, value):
        if self.key == 'auto_answer':
            return {'auto_answer': bool(value),
                    'auto_answer_seconds': value or config.get('auto_answer_seconds', 10)}
        return {self.key: value}

    # @llr LLR-TERM-CONFIG-019, LLR-TERM-AUDIO-009
    def move(self, direction):
        if self.editing:
            self.index = ((self.index+direction) % len(self.options) if self.key == 'ringtone'
                          else max(0, min(len(self.options)-1, self.index+direction)))
        else:
            self.row = (self.row+direction) % len(FIELDS)
        self.error = False

    def change(self, config):
        return self.fields(config, self.options[self.index])
