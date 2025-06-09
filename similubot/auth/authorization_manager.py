"""Authorization manager for SimiluBot."""
import json
import logging
import os
from typing import Dict, List, Optional, Set
import discord

from .permission_types import (
    PermissionLevel, ModulePermission, UserPermissions,
    get_command_module, get_feature_module
)


class AuthorizationManager:
    """
    Manages user permissions and authorization for SimiluBot.
    
    Handles loading and managing user permissions from configuration files,
    provides methods to check permissions, and manages unauthorized access handling.
    """

    def __init__(self, config_path: str = "config/authorization.json", auth_enabled: bool = True):
        """
        Initialize the AuthorizationManager.

        Args:
            config_path: Path to the authorization configuration file
            auth_enabled: Whether authorization is enabled (default: True)
        """
        self.logger = logging.getLogger("similubot.auth")
        self.config_path = config_path
        self.auth_enabled = auth_enabled
        self.user_permissions: Dict[str, UserPermissions] = {}
        self.admin_ids: Set[str] = set()
        self.notify_admins_on_unauthorized: bool = True
        
        # Permission cache for performance
        self._permission_cache: Dict[str, Dict[str, bool]] = {}
        
        if self.auth_enabled:
            self._load_authorization_config()
        else:
            self.logger.info("Authorization system disabled - all users have full access")

    def _load_authorization_config(self) -> None:
        """
        Load authorization configuration from file.
        
        Creates a default configuration file if it doesn't exist.
        """
        if not os.path.exists(self.config_path):
            self._create_default_config()
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Load admin settings
            self.admin_ids = set(str(uid) for uid in config_data.get("admin_ids", []))
            self.notify_admins_on_unauthorized = config_data.get("notify_admins_on_unauthorized", True)
            
            # Load user permissions
            self.user_permissions = {}
            for user_data in config_data.get("users", []):
                user_perms = UserPermissions.from_dict(user_data)
                self.user_permissions[user_perms.user_id] = user_perms
            
            # Add admin users to permissions if not already present
            for admin_id in self.admin_ids:
                if admin_id not in self.user_permissions:
                    self.user_permissions[admin_id] = UserPermissions(
                        user_id=admin_id,
                        permission_level=PermissionLevel.ADMIN,
                        modules=set(ModulePermission),
                        notes="Auto-added administrator"
                    )
            
            self.logger.info(f"Loaded authorization config: {len(self.user_permissions)} users, {len(self.admin_ids)} admins")
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"Error loading authorization config: {e}")
            self.logger.warning("Creating backup and using default configuration")
            self._backup_and_create_default()

    def _create_default_config(self) -> None:
        """Create a default authorization configuration file."""
        default_config = {
            "admin_ids": [],
            "notify_admins_on_unauthorized": True,
            "users": [
                {
                    "user_id": "EXAMPLE_USER_ID_123456789",
                    "permission_level": "full",
                    "modules": ["mega_download", "novelai", "general"],
                    "notes": "Example user with full access - replace with actual user ID"
                },
                {
                    "user_id": "EXAMPLE_USER_ID_987654321",
                    "permission_level": "module",
                    "modules": ["mega_download"],
                    "notes": "Example user with MEGA download access only"
                }
            ]
        }
        
        # Ensure config directory exists
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2)
        
        self.logger.info(f"Created default authorization config at {self.config_path}")
        self.logger.warning("Please update the configuration file with actual user IDs and permissions")

    def _backup_and_create_default(self) -> None:
        """Backup existing config and create a new default one."""
        if os.path.exists(self.config_path):
            backup_path = f"{self.config_path}.backup"
            os.rename(self.config_path, backup_path)
            self.logger.info(f"Backed up invalid config to {backup_path}")
        
        self._create_default_config()

    def is_authorized(self, user_id: str, command_name: Optional[str] = None, 
                     feature_name: Optional[str] = None) -> bool:
        """
        Check if a user is authorized for a command or feature.

        Args:
            user_id: Discord user ID
            command_name: Name of the command (optional)
            feature_name: Name of the feature (optional)

        Returns:
            True if authorized, False otherwise
        """
        # If auth is disabled, everyone has access
        if not self.auth_enabled:
            return True
        
        user_id = str(user_id)
        
        # Check cache first
        cache_key = f"{command_name or feature_name or 'general'}"
        if user_id in self._permission_cache and cache_key in self._permission_cache[user_id]:
            return self._permission_cache[user_id][cache_key]
        
        # Get user permissions
        user_perms = self.user_permissions.get(user_id)
        if not user_perms:
            # User not in config - no access
            result = False
        else:
            # Determine required module
            if command_name:
                required_module = get_command_module(command_name)
            elif feature_name:
                required_module = get_feature_module(feature_name)
            else:
                required_module = ModulePermission.GENERAL_COMMANDS
            
            result = user_perms.has_permission(required_module)
        
        # Cache result
        if user_id not in self._permission_cache:
            self._permission_cache[user_id] = {}
        self._permission_cache[user_id][cache_key] = result
        
        return result

    def is_admin(self, user_id: str) -> bool:
        """
        Check if a user is an administrator.

        Args:
            user_id: Discord user ID

        Returns:
            True if user is admin, False otherwise
        """
        if not self.auth_enabled:
            return True  # When auth is disabled, everyone has admin privileges
        
        user_id = str(user_id)
        return user_id in self.admin_ids or (
            user_id in self.user_permissions and 
            self.user_permissions[user_id].is_admin()
        )

    def get_user_permissions(self, user_id: str) -> Optional[UserPermissions]:
        """
        Get user permissions object.

        Args:
            user_id: Discord user ID

        Returns:
            UserPermissions object or None if user not found
        """
        return self.user_permissions.get(str(user_id))

    def add_user(self, user_id: str, permission_level: PermissionLevel, 
                 modules: Optional[Set[ModulePermission]] = None, notes: str = "") -> bool:
        """
        Add or update a user's permissions.

        Args:
            user_id: Discord user ID
            permission_level: Permission level to assign
            modules: Set of module permissions (optional for full/admin access)
            notes: Optional notes about the user

        Returns:
            True if successful, False otherwise
        """
        try:
            user_id = str(user_id)
            
            if modules is None:
                modules = set()
            
            user_perms = UserPermissions(
                user_id=user_id,
                permission_level=permission_level,
                modules=modules,
                notes=notes
            )
            
            self.user_permissions[user_id] = user_perms
            
            # Clear cache for this user
            if user_id in self._permission_cache:
                del self._permission_cache[user_id]
            
            # Save to file
            self._save_config()
            
            self.logger.info(f"Added/updated user {user_id} with {permission_level.value} access")
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding user {user_id}: {e}")
            return False

    def remove_user(self, user_id: str) -> bool:
        """
        Remove a user's permissions.

        Args:
            user_id: Discord user ID

        Returns:
            True if successful, False otherwise
        """
        try:
            user_id = str(user_id)
            
            if user_id in self.user_permissions:
                del self.user_permissions[user_id]
                
                # Clear cache for this user
                if user_id in self._permission_cache:
                    del self._permission_cache[user_id]
                
                # Save to file
                self._save_config()
                
                self.logger.info(f"Removed user {user_id} from permissions")
                return True
            else:
                self.logger.warning(f"User {user_id} not found in permissions")
                return False
                
        except Exception as e:
            self.logger.error(f"Error removing user {user_id}: {e}")
            return False

    def _save_config(self) -> None:
        """Save current configuration to file."""
        try:
            config_data = {
                "admin_ids": list(self.admin_ids),
                "notify_admins_on_unauthorized": self.notify_admins_on_unauthorized,
                "users": [user_perms.to_dict() for user_perms in self.user_permissions.values()]
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving authorization config: {e}")

    def clear_cache(self) -> None:
        """Clear the permission cache."""
        self._permission_cache.clear()
        self.logger.debug("Permission cache cleared")

    def get_stats(self) -> Dict[str, int]:
        """
        Get authorization statistics.

        Returns:
            Dictionary with authorization statistics
        """
        stats = {
            "total_users": len(self.user_permissions),
            "admin_users": len([u for u in self.user_permissions.values() if u.is_admin()]),
            "full_access_users": len([u for u in self.user_permissions.values() if u.permission_level == PermissionLevel.FULL]),
            "module_access_users": len([u for u in self.user_permissions.values() if u.permission_level == PermissionLevel.MODULE]),
            "no_access_users": len([u for u in self.user_permissions.values() if u.permission_level == PermissionLevel.NONE])
        }
        return stats

