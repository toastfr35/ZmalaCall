"""Built-in TV drivers. Each model family owns a separate directory."""
from importlib import import_module


# Only bundled plugins can be selected; configuration cannot import arbitrary code.
DRIVERS = {'samsung': 'zmala_terminal.linux.tv_plugins.samsung.driver'}


# @llr LLR-TERM-TV-033
def load_driver(name, config):
    """Create an isolated operation instance using the seven-method API."""
    try:
        module = DRIVERS[name]
    except (KeyError, TypeError):
        raise ValueError('Unknown TV driver') from None
    return import_module(module).TVDriver(config)
