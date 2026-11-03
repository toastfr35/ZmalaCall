# @test T-LLT-096
# @requirements LLR-TERM-UI-028
# @environment portable
# @plan Compare update message languages with the supported-language catalogue and verify all activation/check/rollback/error states and unknown-language fallback.
# @pass Every supported locale has nonempty phase-specific text; unknown locales fall back to English.
import json
from pathlib import Path
import unittest
from zmala_terminal.linux.update_screen import MESSAGES,STATES,message

class UpdateMessageTests(unittest.TestCase):
    def test_all_supported_locales_and_states_are_available(self):
        root=Path(__file__).resolve().parents[3]
        languages=json.loads((root/'zmala_terminal/common/shared/terminal-languages.json').read_text(encoding='utf-8'))
        self.assertEqual(set(MESSAGES),set(languages))
        for language in languages:
            for phase in STATES:
                text=message(language,phase);self.assertTrue(text);self.assertIn('Zmala',text) if phase!='checking' else None
        self.assertEqual(message('unknown','updating'),message('en','updating'))
