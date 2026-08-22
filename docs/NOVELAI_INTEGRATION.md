# NovelAI integration

SimiluBot exposes NovelAI through Discord application commands. Generation is a direct human action and sends one image back to Discord; there is no background queue or third-party upload.

## Configuration

Store the persistent API token outside YAML:

```dotenv
NOVELAI_KEY=...
```

The bot loads a project `.env` and then `~/.env` without overriding existing environment variables.

```yaml
discord:
  # Optional while developing; guild commands sync immediately.
  command_guild_id: "123456789012345678"

authorization:
  admin_ids:
    - "123456789012345678"

novelai:
  base_url: "https://image.novelai.net"
  default_model: "nai-diffusion-5-curated"
  state_path: "data/novelai.sqlite3"
  timeout: 120
```

`authorization.admin_ids` is the administrator source. Disabling the legacy authorization system does not make every user a NovelAI administrator.

When upgrading, move any old `authorization.json` admin IDs into this YAML list; the JSON field is intentionally no longer read.

## Commands

- `/nai draw` generates one image. Command options override the user's saved defaults once.
- `/nai defaults show|set|reset` manages global per-user defaults keyed by Discord ID.
- `/nai artist save|delete|list` manages literal, single-pass `$name$` prompt macros.
- `/nai quota` shows the shared Opus pool; only admins see Anlas.
- `/nai admin status|policy|allow|revoke` manages per-guild access.

New guilds start enabled with a user allowlist and all channels allowed. Admins bypass allowlists, but not a disabled guild policy. A channel allowlist also recognizes a thread's parent channel.

Changing a UC preset clears an older custom UC unless a new custom value is supplied in the same command. `$$` produces a literal dollar sign; macro expansion never recursively interprets an artist string.

## Spending boundary

Before generation the bot reads `GET https://image.novelai.net/user/subscription`. It refuses a request that may spend Anlas unless a configured admin explicitly sets `allow_paid:true`. The local check covers inactive/non-Opus accounts, an unavailable Opus pool, dimensions above 1024×1024, and more than 28 steps. NovelAI does not expose a server-side “never spend” transaction flag, so this is a conservative preflight rather than a billing guarantee.

## Architecture

`similubot/novelai/domain.py` owns model profiles, validation, macros, and request construction. `client.py` owns HTTP and ZIP decoding. `store.py` owns SQLite. `service.py` coordinates policy and spending checks. `similubot/commands/nai.py` only translates Discord interactions.

V5 Curated and Full use `params_version=4`, structured V4 prompts, and V5 tag hints. V4.5 remains available through profiles using `params_version=3`; it does not duplicate the generation pipeline.
