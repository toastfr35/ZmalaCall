"""Background polling: captured inputs in, named queue results out.

No worker owns Tk state, timers or hardware. The UI scheduler owns busy flags and
rejects obsolete enrollment generations before applying these results.
"""
from copy import deepcopy
import logging
import threading
from typing import NamedTuple


class ConfigurationResult(NamedTuple):
    generation: int
    config: dict
    callback_revision: int


class NetworkResult(NamedTuple):
    generation: int
    available: bool | None


def poll_network(messages, generation, probe):
    def worker():
        try:
            available = probe()
        except Exception:
            available = None
        messages.put(('poll-network', NetworkResult(generation, available)))
        messages.put(('network-done', generation))
    threading.Thread(target=worker, daemon=True).start()


# @llr LLR-TERM-COM-007, LLR-TERM-COM-008
def poll_configuration(messages, configuration, generation, callback_revision, status):
    # Detach nested diagnostic values too; later UI updates cannot change a report.
    snapshot = deepcopy(status)
    def worker():
        try:
            config = configuration.fetch()
            messages.put(('poll-config', ConfigurationResult(generation, config, callback_revision)))
            if not configuration.cancelled:
                # @llr LLR-TERM-MAINT-018
                configuration.report(snapshot)
        except Exception as error:
            logging.warning('Management connection: %s', error)
        finally:
            messages.put(('poll-done', generation))
    threading.Thread(target=worker, daemon=True).start()
