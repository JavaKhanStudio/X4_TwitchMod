"""Event sources for the Twitch bridge."""

from ..config import Config
from .base import Source
from .stdin import StdinSource


def make_source(config: Config) -> Source:
    if config.source == "stdin":
        return StdinSource()
    if config.source == "twitch":
        from .twitch import TwitchSource  # imported lazily; may need extra deps
        return TwitchSource(config)
    raise ValueError(f"unknown source: {config.source!r} (use 'stdin' or 'twitch')")
