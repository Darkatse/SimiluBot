"""Tests for the authorization system."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from similubot.auth.authorization_manager import AuthorizationManager
from similubot.auth.permission_types import (
    PermissionLevel, ModulePermission, UserPermissions,
    get_command_module, get_feature_module
)
from similubot.auth.unauthorized_handler import UnauthorizedAccessHandler


class TestPermissionTypes(unittest.TestCase):
    """Test cases for permission types and enums."""

    def test_permission_level_enum(self):
        """Test PermissionLevel enum values."""
        assert PermissionLevel.NONE.value == "none"
        assert PermissionLevel.MODULE.value == "module"
        assert PermissionLevel.FULL.value == "full"
        assert PermissionLevel.ADMIN.value == "admin"

    def test_module_permission_enum(self):
        """Test ModulePermission enum values."""
        assert ModulePermission.MEGA_DOWNLOAD.value == "mega_download"
        assert ModulePermission.NOVELAI_GENERATION.value == "novelai"
        assert ModulePermission.GENERAL_COMMANDS.value == "general"

    def test_user_permissions_creation(self):
        """Test UserPermissions creation and validation."""
        # Test basic creation
        user_perms = UserPermissions(
            user_id="123456789",
            permission_level=PermissionLevel.MODULE,
            modules={ModulePermission.MEGA_DOWNLOAD},
            notes="Test user"
        )
        
        assert user_perms.user_id == "123456789"
        assert user_perms.permission_level == PermissionLevel.MODULE
        assert ModulePermission.MEGA_DOWNLOAD in user_perms.modules
        assert user_perms.notes == "Test user"

    def test_user_permissions_full_access(self):
        """Test that full access includes all modules."""
        user_perms = UserPermissions(
            user_id="123456789",
            permission_level=PermissionLevel.FULL,
            modules=set()  # Empty set should be populated with all modules
        )
        
        assert user_perms.permission_level == PermissionLevel.FULL
        assert len(user_perms.modules) == len(ModulePermission)
        assert all(module in user_perms.modules for module in ModulePermission)

    def test_user_permissions_has_permission(self):
        """Test permission checking logic."""
        # Module-specific user
        module_user = UserPermissions(
            user_id="123456789",
            permission_level=PermissionLevel.MODULE,
            modules={ModulePermission.MEGA_DOWNLOAD}
        )
        
        assert module_user.has_permission(ModulePermission.MEGA_DOWNLOAD)
        assert not module_user.has_permission(ModulePermission.NOVELAI_GENERATION)
        
        # Full access user
        full_user = UserPermissions(
            user_id="987654321",
            permission_level=PermissionLevel.FULL,
            modules=set()
        )
        
        assert full_user.has_permission(ModulePermission.MEGA_DOWNLOAD)
        assert full_user.has_permission(ModulePermission.NOVELAI_GENERATION)
        assert full_user.has_permission(ModulePermission.GENERAL_COMMANDS)
        
        # No access user
        no_access_user = UserPermissions(
            user_id="111111111",
            permission_level=PermissionLevel.NONE,
            modules=set()
        )
        
        assert not no_access_user.has_permission(ModulePermission.MEGA_DOWNLOAD)
        assert not no_access_user.has_permission(ModulePermission.NOVELAI_GENERATION)

    def test_user_permissions_serialization(self):
        """Test UserPermissions to/from dict conversion."""
        user_perms = UserPermissions(
            user_id="123456789",
            permission_level=PermissionLevel.MODULE,
            modules={ModulePermission.MEGA_DOWNLOAD, ModulePermission.GENERAL_COMMANDS},
            notes="Test serialization"
        )
        
        # Test to_dict
        data = user_perms.to_dict()
        assert data["user_id"] == "123456789"
        assert data["permission_level"] == "module"
        assert "mega_download" in data["modules"]
        assert "general" in data["modules"]
        assert data["notes"] == "Test serialization"
        
        # Test from_dict
        restored_perms = UserPermissions.from_dict(data)
        assert restored_perms.user_id == user_perms.user_id
        assert restored_perms.permission_level == user_perms.permission_level
        assert restored_perms.modules == user_perms.modules
        assert restored_perms.notes == user_perms.notes

    def test_command_module_mapping(self):
        """Test command to module mapping."""
        assert get_command_module("mega") == ModulePermission.MEGA_DOWNLOAD
        assert get_command_module("about") == ModulePermission.GENERAL_COMMANDS
        assert get_command_module("unknown_command") == ModulePermission.GENERAL_COMMANDS

    def test_feature_module_mapping(self):
        """Test feature to module mapping."""
        assert get_feature_module("mega_auto_detection") == ModulePermission.MEGA_DOWNLOAD
        assert get_feature_module("unknown_feature") == ModulePermission.GENERAL_COMMANDS


class TestAuthorizationManager(unittest.TestCase):
    """Test cases for AuthorizationManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test_auth.json")

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.config_path):
            os.unlink(self.config_path)
        os.rmdir(self.temp_dir)

    def test_auth_manager_disabled(self):
        """Test authorization manager with auth disabled."""
        auth_manager = AuthorizationManager(
            config_path=self.config_path,
            auth_enabled=False
        )
        
        # When auth is disabled, everyone should have access
        assert auth_manager.is_authorized("123456789", command_name="mega")
        assert auth_manager.is_authorized("987654321", feature_name="novelai_generation")
        assert not auth_manager.is_admin("123456789")  # No admin privileges when disabled

    def test_auth_manager_default_config_creation(self):
        """Test that default config is created when file doesn't exist."""
        auth_manager = AuthorizationManager(
            config_path=self.config_path,
            auth_enabled=True
        )
        
        # Config file should be created
        assert os.path.exists(self.config_path)
        
        # Should contain default structure
        with open(self.config_path, 'r') as f:
            config_data = json.load(f)
        
        assert "notify_admins_on_unauthorized" in config_data
        assert "users" in config_data
        assert isinstance(config_data["users"], list)

    def test_auth_manager_user_management(self):
        """Test adding, updating, and removing users."""
        auth_manager = AuthorizationManager(
            config_path=self.config_path,
            auth_enabled=True
        )
        
        # Add a user
        success = auth_manager.add_user(
            user_id="123456789",
            permission_level=PermissionLevel.MODULE,
            modules={ModulePermission.MEGA_DOWNLOAD},
            notes="Test user"
        )
        assert success
        
        # Check user was added
        user_perms = auth_manager.get_user_permissions("123456789")
        assert user_perms is not None
        assert user_perms.permission_level == PermissionLevel.MODULE
        assert ModulePermission.MEGA_DOWNLOAD in user_perms.modules
        
        # Test authorization
        assert auth_manager.is_authorized("123456789", command_name="mega")
        assert not auth_manager.is_authorized("123456789", command_name="nai")
        
        # Update user to full access
        success = auth_manager.add_user(
            user_id="123456789",
            permission_level=PermissionLevel.FULL,
            modules=set(),
            notes="Updated to full access"
        )
        assert success
        
        # Check updated permissions
        user_perms = auth_manager.get_user_permissions("123456789")
        assert user_perms.permission_level == PermissionLevel.FULL
        assert auth_manager.is_authorized("123456789", command_name="nai")
        
        # Remove user
        success = auth_manager.remove_user("123456789")
        assert success
        
        # Check user was removed
        user_perms = auth_manager.get_user_permissions("123456789")
        assert user_perms is None
        assert not auth_manager.is_authorized("123456789", command_name="mega")

    def test_auth_manager_admin_privileges(self):
        """Test admin privilege handling."""
        # Administrators come from the main YAML configuration.
        config_data = {
            "notify_admins_on_unauthorized": True,
            "users": []
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(config_data, f)
        
        auth_manager = AuthorizationManager(
            config_path=self.config_path,
            auth_enabled=True,
            admin_ids=["999999999"],
        )
        
        # Admin identity does not duplicate itself into the mutable user file.
        assert auth_manager.is_admin("999999999")
        user_perms = auth_manager.get_user_permissions("999999999")
        assert user_perms is None
        
        # Admin should have access to everything
        assert auth_manager.is_authorized("999999999", command_name="mega")
        assert auth_manager.is_authorized("999999999", command_name="nai")

    def test_auth_manager_stats(self):
        """Test authorization statistics."""
        auth_manager = AuthorizationManager(
            config_path=self.config_path,
            auth_enabled=True
        )
        
        # Add various users
        auth_manager.add_user("111111111", PermissionLevel.FULL, set())
        auth_manager.add_user("222222222", PermissionLevel.MODULE, {ModulePermission.MEGA_DOWNLOAD})
        auth_manager.add_user("333333333", PermissionLevel.NONE, set())
        auth_manager.add_user("444444444", PermissionLevel.FULL, set())
        
        stats = auth_manager.get_stats()
        assert stats["total_users"] == 4
        assert stats["admin_users"] == 0
        assert stats["full_access_users"] == 2
        assert stats["module_access_users"] == 1
        assert stats["no_access_users"] == 1

    def test_auth_manager_permission_caching(self):
        """Test permission caching functionality."""
        auth_manager = AuthorizationManager(
            config_path=self.config_path,
            auth_enabled=True
        )
        
        # Add a user
        auth_manager.add_user("123456789", PermissionLevel.MODULE, {ModulePermission.MEGA_DOWNLOAD})
        
        # First call should populate cache
        result1 = auth_manager.is_authorized("123456789", command_name="mega")
        assert result1
        
        # Second call should use cache
        result2 = auth_manager.is_authorized("123456789", command_name="mega")
        assert result2
        
        # Cache should be cleared when user is updated
        auth_manager.add_user("123456789", PermissionLevel.NONE, set())
        result3 = auth_manager.is_authorized("123456789", command_name="mega")
        assert not result3


class TestUnauthorizedHandler(unittest.TestCase):
    """Test cases for UnauthorizedAccessHandler."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test_auth.json")
        
        # Create mock bot and auth manager
        self.mock_bot = MagicMock()
        self.auth_manager = AuthorizationManager(
            config_path=self.config_path,
            auth_enabled=True
        )
        
        self.handler = UnauthorizedAccessHandler(
            auth_manager=self.auth_manager,
            bot=self.mock_bot
        )

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.config_path):
            os.unlink(self.config_path)
        os.rmdir(self.temp_dir)

    @pytest.mark.asyncio
    async def test_unauthorized_handler_public_message(self):
        """Test sending public unauthorized message."""
        # Create mock user and channel
        mock_user = MagicMock()
        mock_user.mention = "<@123456789>"
        mock_user.id = "123456789"
        mock_user.display_name = "TestUser"
        
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        
        # Handle unauthorized access
        await self.handler._send_public_unauthorized_message(
            channel=mock_channel,
            user=mock_user,
            command_name="mega"
        )
        
        # Verify message was sent
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        embed = call_args[1]["embed"]
        assert "Unauthorized Access" in embed.title
        assert mock_user.mention in embed.description

    @pytest.mark.asyncio
    async def test_unauthorized_handler_admin_notification(self):
        """Test sending admin notification."""
        # Set up admin
        self.auth_manager.admin_ids.add("999999999")
        
        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "123456789"
        mock_user.display_name = "TestUser"
        mock_user.name = "testuser"
        mock_user.avatar = None
        
        # Create mock admin user
        mock_admin = MagicMock()
        mock_admin.send = AsyncMock()
        self.mock_bot.fetch_user = AsyncMock(return_value=mock_admin)
        
        # Handle unauthorized access
        await self.handler._send_admin_notification(
            user=mock_user,
            command_name="mega"
        )
        
        # Verify admin was notified
        self.mock_bot.fetch_user.assert_called_once_with(999999999)
        mock_admin.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_unauthorized_handler_permission_denied_dm(self):
        """Test sending permission denied DM."""
        # Create mock user
        mock_user = MagicMock()
        mock_user.send = AsyncMock()
        
        # Send permission denied DM
        result = await self.handler.send_permission_denied_dm(
            user=mock_user,
            reason="Test reason"
        )
        
        # Verify DM was sent
        assert result
        mock_user.send.assert_called_once()
        call_args = mock_user.send.call_args
        embed = call_args[1]["embed"]
        assert "Access Denied" in embed.title


if __name__ == "__main__":
    pytest.main([__file__])
