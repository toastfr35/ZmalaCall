"""Installed kiosk diagnostics live in the journal; verbose mode expires in RAM."""
import logging
import os
from pathlib import Path
import sys
import time


def journal_logging():
    return sys.platform == 'linux' and os.environ.get('ZMALA_LOG_STDERR') == '1'


class DiagnosticFilter(logging.Filter):
    def __init__(self, runtime):
        super().__init__()
        self.control = Path(runtime) / 'debug-until'
        self.next_check = 0
        self.until = 0

    # @llr LLR-TERM-MAINT-009, LLR-TERM-MAINT-010
    def filter(self, record):
        now = time.monotonic()
        if now >= self.next_check:
            self.next_check = now + 1
            try:
                self.until = float(self.control.read_text())
            except (OSError, ValueError):
                self.until = 0
        return record.levelno >= logging.INFO or now < self.until


def configure(data):
    if journal_logging():
        handler = logging.StreamHandler()
        handler.addFilter(DiagnosticFilter(os.environ['ZMALA_RUNTIME_DIR']))
        logging.basicConfig(handlers=[handler], level=logging.DEBUG,
                            format='%(levelname)s %(message)s')
    else:
        logging.basicConfig(filename=Path(data) / 'terminal.log', level=logging.INFO,
                            format='%(asctime)s %(levelname)s %(message)s')
