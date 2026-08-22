"""Permission types and enums for SimiluBot authorization system."""
from enum import Enum
from typing import Set, Dict, Any
from dataclasses import dataclass


class PermissionLevel(Enum):
    """Permission levels for users."""
    NONE = "none"           # No access
    MODULE = "module"       # Module-specific access
    FULL = "full"          # Full bot access
    ADMIN = "admin"        # Administrative access


class ModulePermission(Enum):
    """Available module permissions."""
    MEGA_DOWNLOAD = "mega_download"     # MEGA link processing and audio conversion
    NOVELAI_GENERATION = "novelai"     # Legacy config compatibility; /nai has its own policy
    AI_CONVERSATION = "ai_conversation" # AI conversation and assistance
    MUSIC_PLAYBACK = "music_playback"   # Music playback and queue management
    GENERAL_COMMANDS = "general"       # General bot commands (about, help, etc.)


@dataclass
class UserPermissions:
    """User permission configuration."""
    user_id: str
    permission_level: PermissionLevel
    modules: Set[ModulePermission]
    notes: str = ""

    def __post_init__(self):
        """Validate and normalize permissions after initialization."""
        # Convert string permission level to enum if needed
        if isinstance(self.permission_level, str):
            self.permission_level = PermissionLevel(self.permission_level)

        # Convert string modules to enum set if needed
        if isinstance(self.modules, (list, tuple)):
            self.modules = {ModulePermission(m) if isinstance(m, str) else m for m in self.modules}
        elif isinstance(self.modules, set):
            self.modules = {ModulePermission(m) if isinstance(m, str) else m for m in self.modules}

        # Full access includes all modules
        if self.permission_level in (PermissionLevel.FULL, PermissionLevel.ADMIN):
            self.modules = set(ModulePermission)

    def has_permission(self, module: ModulePermission) -> bool:
        """
        Check if user has permission for a specific module.

        Args:
            module: Module to check permission for

        Returns:
            True if user has permission, False otherwise
        """
        # No access
        if self.permission_level == PermissionLevel.NONE:
            return False

        # Full or admin access
        if self.permission_level in (PermissionLevel.FULL, PermissionLevel.ADMIN):
            return True

        # Module-specific access
        if self.permission_level == PermissionLevel.MODULE:
            return module in self.modules

        return False

    def is_admin(self) -> bool:
        """Check if user has administrative privileges."""
        return self.permission_level == PermissionLevel.ADMIN

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "user_id": self.user_id,
            "permission_level": self.permission_level.value,
            "modules": [m.value for m in self.modules],
            "notes": self.notes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPermissions':
        """Create UserPermissions from dictionary."""
        return cls(
            user_id=str(data["user_id"]),
            permission_level=PermissionLevel(data["permission_level"]),
            modules=set(ModulePermission(m) for m in data.get("modules", [])),
            notes=data.get("notes", "")
        )


# Command to module mapping
COMMAND_MODULE_MAP = {
    # MEGA download commands
    "mega": ModulePermission.MEGA_DOWNLOAD,

    # AI conversation commands
    "ai": ModulePermission.AI_CONVERSATION,

    # Music playback commands
    "music": ModulePermission.MUSIC_PLAYBACK,

    # General commands
    "about": ModulePermission.GENERAL_COMMANDS,
    "help": ModulePermission.GENERAL_COMMANDS,
}


def get_command_module(command_name: str) -> ModulePermission:
    """
    Get the module permission required for a command.

    Args:
        command_name: Name of the command

    Returns:
        Required module permission
    """
    return COMMAND_MODULE_MAP.get(command_name, ModulePermission.GENERAL_COMMANDS)


def get_feature_module(feature_name: str) -> ModulePermission:
    """
    Get the module permission required for a feature.

    Args:
        feature_name: Name of the feature (e.g., "mega_auto_detection")

    Returns:
        Required module permission
    """
    feature_map = {
        "mega_auto_detection": ModulePermission.MEGA_DOWNLOAD,
        "mega_link_processing": ModulePermission.MEGA_DOWNLOAD,
        "audio_conversion": ModulePermission.MEGA_DOWNLOAD,
        "ai_conversation": ModulePermission.AI_CONVERSATION,
        "ai_generation": ModulePermission.AI_CONVERSATION,
        "music_playback": ModulePermission.MUSIC_PLAYBACK,
        "music_queue_management": ModulePermission.MUSIC_PLAYBACK
    }
    return feature_map.get(feature_name, ModulePermission.GENERAL_COMMANDS)
