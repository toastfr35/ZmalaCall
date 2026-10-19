"""Transient hardware readiness errors shared by media and call orchestration."""


# @llr LLR-TERM-AUDIO-005
class MediaNotReady(RuntimeError):
    """Keep the cancellable call waiting while its required C20 wakes up."""
