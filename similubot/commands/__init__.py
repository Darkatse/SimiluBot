"""Command modules for SimiluBot."""

from .mega_commands import MegaCommands
from .nai import NaiCog
from .auth_commands import AuthCommands
from .general_commands import GeneralCommands
from .ai_commands import AICommands
from .music_commands import MusicCommands

__all__ = [
    "MegaCommands",
    "NaiCog",
    "AuthCommands",
    "GeneralCommands",
    "AICommands",
    "MusicCommands"
]
