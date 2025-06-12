"""Configuration manager for SimiluBot."""
import logging
import os
from typing import Any, Dict, List, Optional
import yaml
from dotenv import load_dotenv

class ConfigManager:
    """
    Configuration manager for SimiluBot.

    Handles loading and accessing configuration values from the config file.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize the ConfigManager.

        Args:
            config_path: Path to the configuration file

        Raises:
            FileNotFoundError: If the configuration file does not exist
            yaml.YAMLError: If the configuration file is not valid YAML
        """
        self.logger = logging.getLogger("similubot.config")
        self.config_path = config_path
        self.config: Dict[str, Any] = {}

        # Load environment variables from .env file
        load_dotenv()

        self._load_config()

    def _load_config(self) -> None:
        """
        Load the configuration from the config file.

        Raises:
            FileNotFoundError: If the configuration file does not exist
            yaml.YAMLError: If the configuration file is not valid YAML
        """
        if not os.path.exists(self.config_path):
            example_path = f"{self.config_path}.example"
            if os.path.exists(example_path):
                self.logger.error(
                    f"Configuration file {self.config_path} not found. "
                    f"Please copy {example_path} to {self.config_path} and update it."
                )
            else:
                self.logger.error(f"Configuration file {self.config_path} not found.")
            raise FileNotFoundError(f"Configuration file {self.config_path} not found")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as config_file:
                self.config = yaml.safe_load(config_file)
                self.logger.debug(f"Loaded configuration from {self.config_path}")
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing configuration file: {e}")
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: The configuration key (dot notation for nested keys)
            default: Default value to return if the key is not found

        Returns:
            The configuration value or the default value if not found
        """
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                self.logger.debug(f"Configuration key '{key}' not found, using default: {default}")
                return default

        return value

    def get_discord_token(self) -> str:
        """
        Get the Discord bot token.

        Returns:
            The Discord bot token

        Raises:
            ValueError: If the Discord bot token is not set
        """
        token = self.get('discord.token')
        if not token or token == "YOUR_DISCORD_BOT_TOKEN_HERE":
            self.logger.error("Discord bot token not set in configuration")
            raise ValueError("Discord bot token not set in configuration")
        return token

    def get_download_temp_dir(self) -> str:
        """
        Get the temporary directory for downloads.

        Returns:
            The temporary directory path
        """
        return self.get('download.temp_dir', './temp')

    def get_default_bitrate(self) -> int:
        """
        Get the default AAC bitrate.

        Returns:
            The default bitrate in kbps
        """
        return self.get('conversion.default_bitrate', 128)

    def get_supported_formats(self) -> list:
        """
        Get the list of supported input formats.

        Returns:
            List of supported format extensions
        """
        return self.get('conversion.supported_formats', [
            'mp4', 'mp3', 'avi', 'mkv', 'wav', 'flac', 'ogg', 'webm'
        ])

    def get_default_upload_service(self) -> str:
        """
        Get the default upload service (legacy method for backward compatibility).

        Returns:
            The default upload service name
        """
        return self.get('upload.default_service', 'catbox')

    def get_mega_upload_service(self) -> str:
        """
        Get the upload service for MEGA downloads.

        Returns:
            The upload service name for MEGA downloads
        """
        return self.get('upload.mega_downloads', self.get_default_upload_service())

    def get_novelai_upload_service(self) -> str:
        """
        Get the upload service for NovelAI generated images.

        Returns:
            The upload service name for NovelAI images
        """
        return self.get('upload.novelai_images', 'discord')

    def get_catbox_user_hash(self) -> Optional[str]:
        """
        Get the CatBox user hash.

        Returns:
            The CatBox user hash or None if not set
        """
        return self.get('upload.catbox.user_hash', None)

    def get_log_level(self) -> str:
        """
        Get the logging level.

        Returns:
            The logging level
        """
        return self.get('logging.level', 'INFO')

    def get_log_file(self) -> Optional[str]:
        """
        Get the log file path.

        Returns:
            The log file path or None if not set
        """
        return self.get('logging.file', None)

    def get_log_max_size(self) -> int:
        """
        Get the maximum log file size.

        Returns:
            The maximum log file size in bytes
        """
        return self.get('logging.max_size', 10485760)  # 10 MB

    def get_log_backup_count(self) -> int:
        """
        Get the number of backup log files to keep.

        Returns:
            The number of backup log files
        """
        return self.get('logging.backup_count', 5)

    def get_novelai_api_key(self) -> str:
        """
        Get the NovelAI API key.

        Returns:
            The NovelAI API key

        Raises:
            ValueError: If the NovelAI API key is not set
        """
        api_key = self.get('novelai.api_key')
        if not api_key or api_key == "YOUR_NOVELAI_API_KEY_HERE":
            self.logger.error("NovelAI API key not set in configuration")
            raise ValueError("NovelAI API key not set in configuration")
        return api_key

    def is_mega_enabled(self) -> bool:
        """
        Check if MEGA functionality is enabled.

        Returns:
            True if MEGA is enabled, False otherwise
        """
        return self.get('mega.enabled', True)

    def is_auth_enabled(self) -> bool:
        """
        Check if the authorization system is enabled.

        Returns:
            True if authorization is enabled, False otherwise
        """
        return self.get('authorization.enabled', True)

    def get_admin_ids(self) -> list:
        """
        Get the list of administrator Discord IDs.

        Returns:
            List of administrator Discord IDs
        """
        return self.get('authorization.admin_ids', [])

    def get_auth_config_path(self) -> str:
        """
        Get the path to the authorization configuration file.

        Returns:
            Path to the authorization configuration file
        """
        return self.get('authorization.config_path', 'config/authorization.json')

    def should_notify_admins_on_unauthorized(self) -> bool:
        """
        Check if admins should be notified on unauthorized access attempts.

        Returns:
            True if admins should be notified, False otherwise
        """
        return self.get('authorization.notify_admins_on_unauthorized', True)

    def get_novelai_base_url(self) -> str:
        """
        Get the NovelAI API base URL.

        Returns:
            The NovelAI API base URL
        """
        return self.get('novelai.base_url', 'https://image.novelai.net')

    def get_novelai_default_model(self) -> str:
        """
        Get the default NovelAI model.

        Returns:
            The default NovelAI model name
        """
        return self.get('novelai.default_model', 'nai-diffusion-3')

    def get_novelai_timeout(self) -> int:
        """
        Get the NovelAI API request timeout.

        Returns:
            The timeout in seconds
        """
        return self.get('novelai.timeout', 120)

    def get_novelai_default_parameters(self) -> Dict[str, Any]:
        """
        Get the default NovelAI generation parameters.

        Returns:
            Dictionary of default parameters
        """
        return self.get('novelai.default_parameters', {
            'width': 832,
            'height': 1216,
            'steps': 28,
            'scale': 5.0,
            'sampler': 'k_euler',
            'n_samples': 1,
            'seed': -1
        })

    # AI Configuration Methods
    def get_env(self, key: str, default: Any = None) -> Any:
        """
        Get an environment variable value.

        Args:
            key: Environment variable name
            default: Default value if not found

        Returns:
            Environment variable value or default
        """
        return os.getenv(key, default)

    def is_ai_enabled(self) -> bool:
        """
        Check if AI functionality is enabled.

        Returns:
            True if AI is enabled, False otherwise
        """
        return self.get('ai.enabled', True)

    def get_default_ai_provider(self) -> str:
        """
        Get the default AI provider.

        Returns:
            Default AI provider name
        """
        return self.get('ai.default_provider', 'openrouter')

    def get_ai_providers(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all configured AI providers.

        Returns:
            Dictionary of provider configurations
        """
        return self.get('ai.providers', {})

    def get_ai_provider_config(self, provider: str) -> Dict[str, str]:
        """
        Get configuration for a specific AI provider.

        Args:
            provider: Provider name (dynamically loaded from config)

        Returns:
            Dictionary with provider configuration

        Raises:
            ValueError: If provider is not supported or not configured
        """
        # Get provider configuration from YAML
        providers = self.get_ai_providers()

        if provider not in providers:
            raise ValueError(f"AI provider '{provider}' not found in configuration")

        provider_config = providers[provider]

        # Check if provider is enabled
        if not provider_config.get('enabled', True):
            raise ValueError(f"AI provider '{provider}' is disabled")

        # Get credentials from environment variables
        provider_upper = provider.upper()
        base_url = self.get_env(f'{provider_upper}_BASE_URL')
        api_key = self.get_env(f'{provider_upper}_KEY')

        if not base_url or not api_key:
            raise ValueError(f"AI provider '{provider}' credentials not found in environment variables")

        # Get model from YAML config
        model = provider_config.get('model')
        if not model:
            raise ValueError(f"AI provider '{provider}' model not specified in configuration")

        return {
            'base_url': base_url,
            'api_key': api_key,
            'model': model
        }

    def get_ai_max_tokens(self) -> int:
        """
        Get the maximum tokens for AI responses.

        Returns:
            Maximum tokens
        """
        return self.get('ai.default_parameters.max_tokens', 2048)

    def get_ai_temperature(self) -> float:
        """
        Get the AI temperature setting.

        Returns:
            Temperature value
        """
        return self.get('ai.default_parameters.temperature', 0.7)

    def get_ai_conversation_timeout(self) -> int:
        """
        Get the conversation timeout in seconds.

        Returns:
            Timeout in seconds
        """
        return self.get('ai.default_parameters.conversation_timeout', 1800)  # 30 minutes

    def get_ai_max_conversation_history(self) -> int:
        """
        Get the maximum conversation history length.

        Returns:
            Maximum number of messages to keep in history
        """
        return self.get('ai.default_parameters.max_conversation_history', 10)

    def get_ai_default_system_prompt(self) -> str:
        """
        Get the default system prompt for AI conversations.

        Returns:
            Default system prompt
        """
        return self.get(
            'ai.system_prompts.default',
            'You are a helpful AI assistant integrated into a Discord bot. '
            'Provide clear, concise, and helpful responses to user questions and requests.'
        )

    def get_ai_danbooru_system_prompt(self) -> str:
        """
        Get the system prompt for Danbooru tag generation mode.

        Returns:
            Danbooru system prompt
        """
        return self.get(
            'ai.system_prompts.danbooru',
            'You are an expert at analyzing image descriptions and converting them into Danbooru-style tags. '
            'When given a description, respond with a comma-separated list of relevant Danbooru tags that would '
            'help generate or find similar images. Focus on: character features, clothing, poses, settings, '
            'art style, and quality tags. Be specific and use established Danbooru tag conventions.'
        )

    def is_ai_configured(self) -> bool:
        """
        Check if AI functionality is properly configured.

        Returns:
            True if at least one AI provider is configured, False otherwise
        """
        if not self.is_ai_enabled():
            return False

        providers = self.get_ai_providers()

        for provider_name, provider_config in providers.items():
            if not provider_config.get('enabled', True):
                continue

            try:
                self.get_ai_provider_config(provider_name)
                return True
            except ValueError:
                continue

        return False

    def set_ai_provider(self, provider: str) -> bool:
        """
        Set the default AI provider.

        Args:
            provider: Provider name to set as default

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate provider exists and is configured
            self.get_ai_provider_config(provider)

            # Update the configuration
            self.config['ai']['default_provider'] = provider

            # Save the configuration (would need to implement config saving)
            # For now, this only updates the in-memory config
            self.logger.info(f"Default AI provider set to: {provider}")
            return True

        except (ValueError, KeyError) as e:
            self.logger.error(f"Failed to set AI provider '{provider}': {e}")
            return False

    def set_ai_model(self, provider: str, model: str) -> bool:
        """
        Set the model for a specific AI provider.

        Args:
            provider: Provider name
            model: Model name to set

        Returns:
            True if successful, False otherwise
        """
        try:
            providers = self.get_ai_providers()

            if provider not in providers:
                raise ValueError(f"Provider '{provider}' not found")

            # Update the model
            self.config['ai']['providers'][provider]['model'] = model

            self.logger.info(f"AI provider '{provider}' model set to: {model}")
            return True

        except (ValueError, KeyError) as e:
            self.logger.error(f"Failed to set model for provider '{provider}': {e}")
            return False

    def get_available_ai_providers(self) -> List[str]:
        """
        Get list of available AI providers.

        Returns:
            List of provider names that are enabled and configured
        """
        available = []
        providers = self.get_ai_providers()

        for provider_name, provider_config in providers.items():
            if not provider_config.get('enabled', True):
                continue

            try:
                self.get_ai_provider_config(provider_name)
                available.append(provider_name)
            except ValueError:
                continue

        return available

    # Music Configuration Methods
    def is_music_enabled(self) -> bool:
        """
        Check if music functionality is enabled.

        Returns:
            True if music is enabled, False otherwise
        """
        return self.get('music.enabled', True)

    def get_music_max_queue_size(self) -> int:
        """
        Get the maximum queue size for music.

        Returns:
            Maximum queue size
        """
        return self.get('music.max_queue_size', 100)

    def get_music_max_song_duration(self) -> int:
        """
        Get the maximum song duration in seconds.

        Returns:
            Maximum song duration in seconds
        """
        return self.get('music.max_song_duration', 3600)

    def get_music_auto_disconnect_timeout(self) -> int:
        """
        Get the auto-disconnect timeout in seconds.

        Returns:
            Auto-disconnect timeout in seconds
        """
        return self.get('music.auto_disconnect_timeout', 300)

    def get_music_volume(self) -> float:
        """
        Get the default music volume.

        Returns:
            Default volume (0.0-1.0)
        """
        return self.get('music.volume', 0.5)

    # YouTube PoToken Configuration Methods
    def is_youtube_auto_fallback_enabled(self) -> bool:
        """
        Check if automatic fallback on bot detection is enabled.

        Returns:
            True if auto fallback is enabled, False otherwise
        """
        return self.get('music.youtube.auto_fallback_on_bot_detection', True)

    def is_potoken_enabled(self) -> bool:
        """
        Check if PoToken functionality is enabled.

        Returns:
            True if PoToken is enabled, False otherwise
        """
        return self.get('music.youtube.potoken.enabled', False)

    def is_potoken_auto_generate_enabled(self) -> bool:
        """
        Check if automatic PoToken generation is enabled.

        Returns:
            True if auto generation is enabled, False otherwise
        """
        return self.get('music.youtube.potoken.auto_generate', True)

    def get_potoken_client(self) -> str:
        """
        Get the PoToken client type.

        Returns:
            Client type for PoToken usage
        """
        return self.get('music.youtube.potoken.client', 'WEB')

    def get_manual_visitor_data(self) -> str:
        """
        Get the manual visitor data for PoToken.

        Returns:
            Manual visitor data string
        """
        return self.get('music.youtube.potoken.manual.visitor_data', '')

    def get_manual_po_token(self) -> str:
        """
        Get the manual PoToken.

        Returns:
            Manual PoToken string
        """
        return self.get('music.youtube.potoken.manual.po_token', '')

    def is_potoken_cache_enabled(self) -> bool:
        """
        Check if PoToken caching is enabled.

        Returns:
            True if caching is enabled, False otherwise
        """
        return self.get('music.youtube.potoken.cache_enabled', True)

    def is_fallback_web_client_enabled(self) -> bool:
        """
        Check if WEB client fallback is enabled.

        Returns:
            True if WEB client fallback is enabled, False otherwise
        """
        return self.get('music.youtube.fallback.use_web_client', True)

    def is_manual_potoken_prompt_enabled(self) -> bool:
        """
        Check if manual PoToken prompting is enabled.

        Returns:
            True if manual prompting is enabled, False otherwise
        """
        return self.get('music.youtube.fallback.prompt_for_manual_potoken', False)
