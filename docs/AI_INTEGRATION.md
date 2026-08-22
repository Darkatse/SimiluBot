# AI Integration Documentation

## Overview

SimiluBot now includes comprehensive AI conversation functionality with support for multiple AI providers, conversation memory, and specialized modes. The AI system is designed to be modular, extensible, and follows the existing bot architecture patterns with dynamic configuration management.

## Features

### Core Functionality
- **Multi-Provider Support**: OpenRouter, SiliconFlow, DeepSeek, and other OpenAI-compatible APIs
- **Dynamic Configuration**: YAML-based provider and model configuration with runtime switching
- **Conversation Memory**: Per-user conversation sessions with 30-minute timeout
- **Progress Tracking**: Real-time progress bars during AI processing
- **Specialized Modes**: Default conversation and Danbooru tag generation
- **Authorization Integration**: Full integration with existing permission system
- **Modular Architecture**: Clean separation of concerns with dedicated modules

### Command Structure
- `!ai` - Show help message and current configuration
- `!ai <prompt>` - Default AI conversation with user-provided prompt
- `!ai <prompt> mode:danbooru` - AI art prompt generation mode for Danbooru tags
- `!ai set:provider <name>` - Switch to a different AI provider
- `!ai set:model <name>` - Change model for current provider

## Configuration

The AI system uses a two-tier configuration approach following SimiluBot's existing patterns:

### 1. Environment Variables (.env file) - Credentials Only

Copy `.env.example` to `.env` and configure your API credentials:

```env
# AI Provider Credentials for SimiluBot
# Copy this file to .env and fill in your actual API keys and base URLs
# All other AI configuration (models, parameters, etc.) is in config/config.yaml

# OpenRouter Configuration
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_KEY=your_openrouter_key_here

# SiliconFlow Configuration
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1/
SILICONFLOW_KEY=your_siliconflow_key_here

# DeepSeek Configuration
DEEP_SEEK_BASE_URL=https://api.deepseek.com/v1
DEEP_SEEK_KEY=your_deepseek_key_here

# Add additional AI providers as needed:
# CUSTOM_PROVIDER_BASE_URL=https://api.example.com/v1
# CUSTOM_PROVIDER_KEY=your_custom_key_here
```

### 2. YAML Configuration (config/config.yaml) - Settings & Models

Add AI configuration to your `config/config.yaml` following the existing pattern:

```yaml
# AI Conversation Configuration
ai:
  enabled: true  # Set to false to disable AI functionality
  default_provider: "openrouter"  # Default AI provider (openrouter, siliconflow, deepseek, or custom)
  providers:
    openrouter:
      model: "anthropic/claude-3.5-sonnet"  # Default model for OpenRouter
      enabled: true
    siliconflow:
      model: "deepseek-ai/deepseek-chat"  # Default model for SiliconFlow
      enabled: true
    deepseek:
      model: "deepseek-chat"  # Default model for DeepSeek
      enabled: true
  default_parameters:
    max_tokens: 2048  # Maximum tokens in AI responses
    temperature: 0.7  # AI creativity/randomness (0.0-2.0)
    conversation_timeout: 1800  # Conversation timeout in seconds (30 minutes)
    max_conversation_history: 10  # Maximum messages to keep in conversation history
  system_prompts:
    default: "You are a helpful AI assistant integrated into a Discord bot. Provide clear, concise, and helpful responses to user questions and requests."
    danbooru: "You are an expert at analyzing image descriptions and converting them into Danbooru-style tags. When given a description, respond with a comma-separated list of relevant Danbooru tags that would help generate or find similar images. Focus on: character features, clothing, poses, settings, art style, and quality tags. Be specific and use established Danbooru tag conventions."
```

### 3. Authorization Configuration

Add AI permissions to your `config/authorization.json`:

```json
{
  "admin_ids": ["123456789012345678"],
  "notify_admins_on_unauthorized": true,
  "users": [
    {
      "user_id": "EXAMPLE_USER_ID_123456789",
      "permission_level": "full",
      "modules": [
        "mega_download",
        "ai_conversation",
        "general"
      ],
      "notes": "Example user with full access including AI"
    },
    {
      "user_id": "EXAMPLE_USER_ID_555666777",
      "permission_level": "module",
      "modules": [
        "ai_conversation",
        "general"
      ],
      "notes": "Example user with AI conversation access only"
    }
  ]
}
```

## Architecture

### Module Structure

```
similubot/ai/
├── __init__.py              # Module exports
├── ai_client.py             # OpenAI-compatible API client
├── conversation_memory.py   # User conversation memory management
└── ai_tracker.py           # Progress tracking for AI operations

similubot/commands/
└── ai_commands.py          # Discord command integration
```

### Key Components

#### AIClient (`ai_client.py`)
- OpenAI-compatible API client supporting multiple providers
- Async/await support for non-blocking operations
- Streaming and standard response generation
- Connection testing and error handling

#### ConversationMemory (`conversation_memory.py`)
- Per-user conversation sessions with automatic timeout
- Mode-specific system prompts (default, danbooru)
- Message history management with configurable limits
- Background cleanup of expired conversations

#### AITracker (`ai_tracker.py`)
- Real-time progress tracking for AI operations
- Token-based progress calculation
- Integration with Discord progress updater
- Detailed generation statistics

#### AICommands (`ai_commands.py`)
- Discord command handler following existing patterns
- Argument parsing for modes and prompts
- Progress tracking integration
- Error handling and user feedback

## Usage Examples

### Basic Conversation
```
!ai Hello, how are you today?
!ai What is the weather like in Tokyo?
!ai Can you help me write a Python function?
```

### Danbooru Tag Generation
```
!ai mode:danbooru anime girl with blue hair and red eyes
!ai mode:danbooru cyberpunk cityscape at night
!ai mode:danbooru fantasy landscape with mountains
```

### Dynamic Configuration
```
!ai set:provider openrouter          # Switch to OpenRouter
!ai set:provider siliconflow         # Switch to SiliconFlow
!ai set:provider deepseek            # Switch to DeepSeek
!ai set:model anthropic/claude-3.5-sonnet    # Change model for current provider
!ai set:model deepseek-ai/deepseek-chat      # Change to different model
```

### Help and Information
```
!ai                    # Show help message with current configuration
!status               # Includes AI statistics and active conversations
!about                # Shows AI availability and provider info
```

## Integration with Existing Systems

### Authorization
AI commands respect the existing authorization system:
- Commands require the "ai" permission
- Admin-only features follow existing patterns
- Unauthorized access triggers standard notifications

### Progress Tracking
AI operations use the existing progress tracking system:
- Real-time Discord embed updates
- Consistent progress bar formatting
- Integration with existing updater classes

### Configuration Management
AI configuration extends the existing ConfigManager:
- Environment variable support via python-dotenv
- Backward compatibility with existing config patterns
- Validation and error handling

### Command Registry
AI commands integrate with the existing command registry:
- Automatic registration when configured
- Help system integration
- Consistent error handling patterns

## Testing

### Unit Tests
Run the comprehensive test suite:
```bash
python -m pytest tests/test_ai_functionality.py -v
```

### Integration Testing
Test the AI components without Discord:
```bash
python test_ai_integration.py
```

### Manual Testing
1. Configure your .env file with valid API keys
2. Start the bot: `python main.py`
3. Test basic conversation: `!ai Hello!`
4. Test Danbooru mode: `!ai mode:danbooru anime girl`

## Troubleshooting

### Common Issues

#### AI Commands Not Available
- Check that at least one AI provider is configured in .env
- Verify API keys are valid and have sufficient credits
- Check bot logs for configuration errors

#### Conversation Memory Issues
- Conversations automatically expire after 30 minutes
- Mode switching clears conversation history
- Check memory statistics with `!status`

#### Progress Tracking Problems
- Progress updates every 2 seconds during generation
- Long responses may take time to complete
- Check for rate limiting from AI providers

### Debug Logging
Enable debug logging to troubleshoot issues:
```yaml
# config/config.yaml
logging:
  level: "DEBUG"
```

## Security Considerations

### API Key Management
- Store API keys in .env file (not in code)
- Add .env to .gitignore
- Use environment-specific keys for development/production

### Rate Limiting
- AI providers have rate limits and usage quotas
- Implement user-level rate limiting if needed
- Monitor usage through provider dashboards

### Content Filtering
- AI responses are not filtered by default
- Consider implementing content moderation for public bots
- Review provider terms of service for content policies

## Future Enhancements

### Planned Features
- Image analysis and description
- File upload support for context
- Custom model fine-tuning
- Multi-language support
- Voice message transcription

### Extension Points
- Additional AI providers (Anthropic, Google, etc.)
- Custom system prompt management
- Conversation export/import
- Advanced memory management
- Plugin system for specialized modes

## Dependencies

### New Dependencies
- `openai>=1.0.0` - OpenAI-compatible API client
- `python-dotenv>=1.0.0` - Environment variable management
- `aiohttp>=3.8.0` - Async HTTP client support

### Compatibility
- Python 3.8+
- Discord.py 2.0+
- Existing SimiluBot dependencies
