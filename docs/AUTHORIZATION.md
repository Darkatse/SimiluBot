# SimiluBot Authorization System

The SimiluBot authorization system provides comprehensive user permission management with granular control over bot features and commands.

## Overview

The authorization system consists of three main components:

1. **Permission Types** - Defines permission levels and module permissions
2. **Authorization Manager** - Manages user permissions and authorization checks
3. **Unauthorized Handler** - Handles unauthorized access attempts and admin notifications

## Permission Levels

### Available Permission Levels

- **`none`** - No access to any bot features
- **`module`** - Access to specific modules only
- **`full`** - Full access to all bot features
- Administrators are listed in `config.yaml`; they are not a mutable permission level

### Module Permissions

- **`mega_download`** - MEGA link processing and audio conversion
- **`novelai`** - Legacy value accepted when reading old files; `/nai` now uses its guild policy
- **`music_playback`** - Music playback and queue management
- **`general`** - General bot commands (about, help, etc.)

## Configuration

### Main Configuration (config.yaml)

```yaml
# Authorization Configuration
authorization:
  enabled: true  # Set to false to disable authorization (all users have access)
  admin_ids:  # List of Discord user IDs with administrative privileges
    - "123456789012345678"  # Replace with actual Discord user IDs
  config_path: "config/authorization.json"  # Path to authorization config file
  notify_admins_on_unauthorized: true  # Notify admins when unauthorized access is attempted
```

### Authorization Configuration (config/authorization.json)

The authorization configuration file is automatically created with example users:

```json
{
  "notify_admins_on_unauthorized": true,
  "users": [
    {
      "user_id": "EXAMPLE_USER_ID_123456789",
      "permission_level": "full",
      "modules": ["mega_download", "general"],
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
```

## Admin Commands

Administrators can manage user permissions using the following commands:

### View Authorization Status

```
!auth status
```

Shows authorization system status and user statistics.

### View User Permissions

```
!auth user <user_id>
```

Shows detailed permissions for a specific user.

### Add/Update User Permissions

```
!auth add <user_id> <level> [modules...]
```

**Examples:**
```
!auth add 123456789012345678 full
!auth add 987654321098765432 module mega_download
!auth add 999888777666555444 none
```

**Permission Levels:**
- `full` - Full access to all features
- `module` - Access to specified modules only
- `none` - No access

**Available Modules:**
- `mega_download` - MEGA link processing
- `novelai` - Legacy compatibility only; use `/nai admin` for image access
- `music_playback` - Music playback and queue management
- `general` - General commands

### Remove User

```
!auth remove <user_id>
```

Removes a user from the authorization system.

## Protected Features

### Commands

- **`!mega`** - Requires `mega_download` module permission
- **`/nai`** - Uses the independent per-guild user/channel policy described in `NOVELAI_INTEGRATION.md`
- **`!music`** - Requires `music_playback` module permission
- **`!about`** - Requires `general` module permission (usually granted to all users)

### Automatic Features

- **MEGA Auto-Detection** - Requires `mega_download` module permission
- **Image Generation** - Requires `novelai` module permission

## Unauthorized Access Handling

When a user attempts to access a restricted feature:

1. **Public Response** - A public message is sent to the channel explaining the access denial
2. **Admin Notification** - Administrators receive a private message with:
   - User information
   - Attempted action
   - Quick action commands to grant permissions
3. **Logging** - The attempt is logged for security monitoring

### Example Unauthorized Access Notification

Administrators receive detailed notifications including:

```
🚨 Unauthorized Access Attempt

👤 User: TestUser (@testuser)
ID: 123456789012345678

🎯 Attempted Action: Command: mega
Required: MEGA Download

📍 Location: #general
Server: My Discord Server

⚡ Quick Actions:
Grant Full Access: !auth add 123456789012345678 full
Grant Module Access: !auth add 123456789012345678 module mega_download
View User Info: !auth user 123456789012345678
```

## Security Features

### Permission Caching

- Permissions are cached for performance
- Cache is automatically cleared when permissions are updated
- Prevents excessive file I/O during authorization checks

### Admin Protection

- Admin users are automatically added to the authorization system
- Admin privileges cannot be accidentally removed through normal commands
- Multiple admin users are supported

### Audit Trail

- All permission changes are logged with timestamps
- User notes track who made changes and when
- Failed authorization attempts are logged for security monitoring

## Disabling Authorization

To disable the authorization system entirely:

1. Set `authorization.enabled: false` in `config.yaml`
2. Restart the bot

When disabled:
- All users have full access to all features
- No authorization checks are performed
- Admin commands are still restricted (no admin privileges when disabled)

## Best Practices

### Initial Setup

1. Add your Discord user ID to `admin_ids` in the configuration
2. Test the authorization system with a test user
3. Grant permissions gradually based on user needs

### Permission Management

1. Use `module` level permissions for most users
2. Reserve `full` access for trusted users
3. Use `admin` level sparingly for bot administrators only
4. Regularly review user permissions

### Security

1. Keep the authorization configuration file secure
2. Monitor unauthorized access attempts
3. Use descriptive notes when adding users
4. Regularly audit user permissions

## Troubleshooting

### Common Issues

**Bot not responding to commands:**
- Check if authorization is enabled
- Verify user has appropriate permissions
- Check bot logs for authorization errors

**Admin commands not working:**
- Verify your Discord user ID is in `admin_ids`
- Ensure authorization is enabled
- Check that you have admin permissions

**Configuration file errors:**
- The system will create a backup and use defaults if the config is invalid
- Check logs for configuration loading errors
- Verify JSON syntax in authorization.json

### Getting User IDs

To get a Discord user ID:
1. Enable Developer Mode in Discord settings
2. Right-click on a user
3. Select "Copy ID"

## API Reference

### AuthorizationManager

```python
# Check if user is authorized
is_authorized(user_id: str, command_name: str = None, feature_name: str = None) -> bool

# Check if user is admin
is_admin(user_id: str) -> bool

# Add/update user permissions
add_user(user_id: str, permission_level: PermissionLevel, modules: Set[ModulePermission], notes: str) -> bool

# Remove user
remove_user(user_id: str) -> bool

# Get user permissions
get_user_permissions(user_id: str) -> Optional[UserPermissions]
```

### Permission Types

```python
# Permission levels
PermissionLevel.NONE
PermissionLevel.MODULE
PermissionLevel.FULL
PermissionLevel.ADMIN

# Module permissions
ModulePermission.MEGA_DOWNLOAD
ModulePermission.NOVELAI_GENERATION
ModulePermission.GENERAL_COMMANDS
```
