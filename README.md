# SimiluBot

A Discord bot that downloads media from MEGA links, converts them to AAC format, and uploads them to CatBox or Discord.

## Features

- Automatically detects MEGA links in Discord messages
- Downloads media files from MEGA links
- Converts media files to AAC format with configurable bitrate
- Uploads converted files to CatBox (default) or Discord
- Generates NovelAI V5 images with per-user defaults and artist macros
- Applies per-guild user/channel allowlists to NovelAI commands
- Supports various input formats (MP4, MP3, AVI, MKV, etc.)
- Modular and extensible architecture

## Requirements

- Python 3.10 or higher
- FFmpeg (must be installed and available in PATH)
- Discord Bot Token
- MEGA account (optional, for better download speeds)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/Darkatse/SimiluBot.git
   cd SimiluBot
   ```

2. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a configuration file:
   ```
   cp config/config.yaml.example config/config.yaml
   ```

4. Edit the configuration file and add your Discord bot token:
   ```yaml
   discord:
     token: "YOUR_DISCORD_BOT_TOKEN_HERE"
   ```

5. Put your NovelAI persistent API token in `~/.env` if image generation is enabled:
   ```dotenv
   NOVELAI_KEY=...
   ```

## Configuration

The `config/config.yaml` file contains all the configuration options for the bot:

- `DISCORD_TOKEN`: Preferred Discord bot token source; `discord.token` remains a YAML fallback
- `discord.command_prefix`: Command prefix for the bot (default: `!`)
- `discord.message_content_intent`: Enable only when legacy prefix commands are needed
- `discord.command_guild_id`: Optional guild for immediate slash-command sync during development
- `authorization.admin_ids`: Users allowed to manage NovelAI access and paid generation
- `novelai.state_path`: SQLite storage for preferences, macros, and access policy
- `download.temp_dir`: Directory to store temporary files
- `conversion.default_bitrate`: Default AAC bitrate in kbps (default: `128`)
- `conversion.supported_formats`: List of supported input formats
- `upload.default_service`: Default upload service (`catbox` or `discord`)
- `upload.catbox.user_hash`: CatBox user hash (optional)
- `logging.level`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `logging.file`: Log file path
- `logging.max_size`: Maximum log file size in bytes
- `logging.backup_count`: Number of backup log files to keep

## Usage

1. Start the bot:
   ```
   python main.py
   ```

2. In Discord, you can use the following commands:
   - `!mega <url> [bitrate]`: Download a file from MEGA and convert it to AAC format
   - `/nai draw`: Generate an image with NovelAI V5
   - `/nai defaults`, `/nai artist`, `/nai quota`: Manage personal generation choices
   - `/nai admin`: Manage guild access (configured admins only)
   - `!about`: Show information about the bot

The bot will also automatically detect and process MEGA links in messages.

## Docker Compose

```bash
cp .env.example .env
cp config/config.docker.yaml.example config/config.yaml
docker compose up -d --build
docker compose logs -f bot
```

Set `DISCORD_TOKEN` and `NOVELAI_KEY` in `.env`, then replace the guild and administrator IDs in `config/config.yaml`. Runtime state is kept in the Compose `data` volume.

## Project Structure

```
SimiluBot/
├── config/
│   └── config.yaml
├── similubot/
│   ├── bot.py                 # Main Discord bot implementation
│   ├── novelai/               # Protocol, service, and SQLite state
│   ├── commands/nai.py        # NovelAI slash-command UI
│   ├── downloaders/
│   │   └── mega_downloader.py # MEGA download functionality
│   ├── converters/
│   │   └── audio_converter.py # FFmpeg audio conversion
│   ├── uploaders/
│   │   ├── catbox_uploader.py # CatBox upload functionality
│   │   └── discord_uploader.py # Discord upload functionality
│   └── utils/
│       ├── config_manager.py  # Configuration management
│       └── logger.py          # Logging functionality
├── tests/                     # Unit tests
├── .gitignore
├── README.md
├── requirements.txt
└── main.py                    # Entry point
```

## Development

### Running Tests

```
pytest
```

### Adding New Features

The modular architecture makes it easy to add new features:

- Add new downloaders in `similubot/downloaders/`
- Add new converters in `similubot/converters/`
- Add new uploaders in `similubot/uploaders/`

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper for Python
- [mega.py](https://github.com/odwyersoftware/mega.py) - Python library for the MEGA API
- [FFmpeg](https://ffmpeg.org/) - Audio/video conversion tool
