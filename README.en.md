# Hermes Feishu Streaming Card Plugin V3.3.0

[中文](README.md) | [English](README.en.md)

![Hermes Feishu Streaming Card cover](docs/assets/readme-cover.png)

Provides stable streaming card messages for the Feishu/Lark platform adapter in Hermes Agent Gateway. V3.3.0 uses a **sidecar-only** architecture: Hermes receives only a minimal hook, while Feishu CardKit rendering, session state, update throttling, retries, health metrics, and fault isolation live in an independent sidecar process. New in V3.3.0: in-process multi-profile support — one sidecar can serve multiple Hermes profiles, each with independent Feishu credentials and bot routing.

The current release has completed the real Feishu E2E main flow: each new user message creates a new card, thinking and final answers update progressively in that same card, tool calls are tracked in real time, the completed card shows duration/model/token/context metadata, and Hermes no longer emits duplicate gray native text messages after the card is delivered.

The Feishu CardKit HTTP client is implemented and covered by a mock Feishu server, real Feishu smoke tests, real Hermes Gateway E2E testing, and long-card stress testing.

Real card screenshot:

![Real Feishu streaming card screenshot](docs/assets/feishu-weather-card.png)

## Core Features

- **Streaming thinking**: accumulates `thinking.delta` content and filters `<think>`/`</think>` and DeepSeek `<thinking>`/`</thinking>` tags
- **Progressive answer updates**: streams `answer.delta` into one card and replaces thinking content with the final answer on completion
- **Tool call tracking**: `tool.updated` shows real-time tool call counts and status, retains cumulative total on completion
- **Runtime footer**: shows duration, model, input/output tokens, context length, and context percentage by default; non-terminal cards show a rotating braille spinner animation
- **Stable long-text rendering**: splits card body into safe Markdown blocks; real stress testing covered 16k Chinese characters in one Feishu card
- **Table limit protection**: Markdown tables exceeding Feishu's 5-table limit are automatically truncated with a notice appended, preventing card send failures
- **Fault isolation**: when the sidecar is unavailable, the Hermes hook fails open and Hermes native text continues to work
- **Safe installer**: fails closed, checks Hermes version/code shape/backup/manifest before writing
- **Recovery path**: `restore` and `uninstall` refuse to overwrite user-modified Hermes files

## V3.3.0 What's New

V3.3.0 introduces several enhancements on top of V3.2's sidecar-only architecture, focused on multi-environment deployment and stability:

- **Multi-profile in-process support**: One sidecar process can serve multiple Hermes profiles simultaneously, each with independent Feishu credentials (`app_id`/`app_secret`), bot registrations, and routing bindings. Session isolation uses `profile_id:message_id` composite keys, ensuring messages from different profiles never interfere.
- **Per-bot credential routing**: `BotRegistry` supports profile-aware routing, selecting the correct bot credential pool based on `profile_id`. `_client_for_bot()` uses a dict-based factory pattern for per-profile dispatch.
- **DeepSeek chain-of-thought compatibility**: `THINK_TAG_RE` and `THINK_TAGS` now include `<thinking>`/`</thinking>` tags alongside `<think>`/`</think>` for unified normalization, ensuring DeepSeek model reasoning content displays correctly.
- **Card table limit protection**: New `count_markdown_tables()` function and `MAX_CARD_TABLES` constant (default 5). Tables exceeding the limit are automatically truncated with a notice appended, preventing Feishu 11310 errors.
- **Footer spinner animation**: Non-terminal card footer now shows a rotating braille spinner (driven by `time.time()`, no extra API calls) instead of static text, improving visual feedback.
- **Platform check fix**: `_render_complete_hook_block` and `_render_previous_async_complete_hook_block` now gate `return None` behind `source.platform.value == "feishu"`, preventing the complete hook from swallowing responses on QQ/WeChat/DingTalk and other non-Feishu platforms.

## V3.2 Multi-bot And Group Chat

V3.2 adds multi-bot routing and formal group chat support: one sidecar manages multiple Feishu bots and routes cards by `chat_id`/`open_chat_id` to the bound bot. Unbound chats use the fallback/default bot. This plugin does not decide group trigger rules; Hermes still decides when to respond, and the plugin only renders cards for events Hermes already emits.

### Key Features

- **Multi-bot registry**: Define multiple bots under `bots.items` with independent `app_id`/`app_secret`
- **Chat-to-bot bindings**: `bindings.chats` maps `chat_id` → `bot_id`; unmatched chats fall back to `bindings.fallback_bot`
- **Group rules framework**: `bindings.group_rules.enabled` reserved for future filtering (no-op in V3.3.0)
- **Bot management CLI**: `hermes_feishu_card.cli bots` provides `list`/`show`/`add`/`remove`/`bind-chat`/`unbind-chat`
- **Sidecar routing diagnostics**: `/health.routing` exposes `bot_count`, `chat_binding_count`, `last_route`, and bot details
- **Routing context passthrough**: `message.started` fields (`chat_type`, `tenant_key`, `agent_id`, `profile_id`) are extracted and forwarded

### Configuration Steps

1. **Create separate Feishu custom apps** for each bot. Record each app's `app_id` and `app_secret`.
2. **Edit the sidecar config** (default `~/.hermes_feishu_card/config.yaml`):
   - Define each bot under `bots.items` with `name`, `app_id`, `app_secret`
   - Map chat IDs to bot IDs in `bindings.chats`
   - Set `bindings.fallback_bot` to the default bot ID (usually `"default"`)
3. **Restart the sidecar**: `hermes-feishu-card restart` or restart Hermes Gateway
4. **Verify routing**: `python3 -m hermes_feishu_card.cli doctor --config ~/.hermes_feishu_card/config.yaml`
5. **Test**: send a message in a bound group; the card should be sent by the correct bot.


### Full Configuration Example

```yaml
server:
  host: 127.0.0.1
  port: 8765

feishu:
  # Default bot credentials (used for fallback_bot or single-bot mode)
  app_id: ""
  app_secret: ""

bots:
  default: default
  items:
    sales:
      name: "Sales Group Bot"
      app_id: "cli_sales_xxxxx"
      app_secret: "sales_secret_xxx"
    support:
      name: "Support Bot"
      app_id: "cli_support_yyyyy"
      app_secret: "support_secret_xxx"

bindings:
  fallback_bot: default
  chats:
    # Sales group → sales bot
    oc_5cc6a25d8815790fa890dd0226005e83: sales
    # Support group → support bot
    oc_7dd7b36e9826701fb901ee0337007f94: support
  group_rules:
    enabled: false  # V3.3.0 does not filter group triggers

card:
  title: Hermes Agent
  max_wait_ms: 800
  max_chars: 240
  footer_fields:
    - duration
    - model
    - input_tokens
    - output_tokens
    - context
```

> **Note**: `feishu.app_id` / `feishu.app_secret` are only used for the fallback bot or single-bot setups. For multi-bot, provide per-bot credentials to avoid cross-bot permission issues.

### How to Get chat_id

**Important**: `bindings.chats` defaults to empty `{}`. All unbound messages will route to `fallback_bot`. When using multiple bots, you must configure chat_id bindings.

Methods to obtain chat_id:

1. **Extract from Gateway logs** (recommended):
   ```bash
   # Check Gateway logs for chat_id
   grep "chat_id=" ~/.hermes/profiles/*/logs/gateway.log | grep "Inbound" | tail -20
   
   # Example output:
   # ... chat_id=oc_xxxxxxxxxxxxxxxx
   ```

2. **Verify routing via sidecar health check**:
   ```bash
   curl -s http://127.0.0.1:8765/health | jq '.routing.last_route'
   # Output: {"message_id": "...", "chat_id": "oc_xxx", "bot_id": "main", "reason": "bindings.fallback_bot"}
   ```
   If `reason` shows `bindings.fallback_bot`, the chat_id is unbound and needs to be added to config.

3. **From Feishu group URL**: Open the Feishu group chat, the `oc_xxx` in the URL is the chat_id.

### Common Commands

```bash
# List all registered bots
python3 -m hermes_feishu_card.cli bots list --config ~/.hermes_feishu_card/config.yaml

# Show bot details
python3 -m hermes_feishu_card.cli bots show sales --config ~/.hermes_feishu_card/config.yaml

# Bind a chat to a bot
python3 -m hermes_feishu_card.cli bots bind-chat oc_xxxx sales --config ~/.hermes_feishu_card/config.yaml

# Unbind a chat
python3 -m hermes_feishu_card.cli bots unbind-chat oc_xxxx --config ~/.hermes_feishu_card/config.yaml

# Add a new bot
python3 -m hermes_feishu_card.cli bots add --id support --name "Support Bot" --app-id cli_support_xxx --app-secret "xxx" --config ~/.hermes_feishu_card/config.yaml

# Remove a bot
python3 -m hermes_feishu_card.cli bots remove support --config ~/.hermes_feishu_card/config.yaml

# Health check & routing diagnostics
curl http://127.0.0.1:8765/health | jq '.routing'
```

### Troubleshooting

- **Wrong bot replied**: check `bindings.chats` mapping; ensure `chat_id` matches the Feishu group's `oc_...` ID
- **Group card not sent**:
  1. Verify the bot has joined the group and has card-send permissions
  2. Confirm bot has `send_message` and `update_message` API scopes
  3. Ensure Hermes actually triggered a reply (check Hermes logs)
  4. Run `doctor` or inspect `/health.routing` to verify routing is healthy
- **Unknown bot binding**: run `python3 -m hermes_feishu_card.cli doctor` to validate config and credentials
- **Sidecar not running**: `ps aux | grep hermes_feishu_card.runner` or check `hermes logs`

### Routing Logic Details

- Event arrives → `BotRegistry.resolve(RoutingContext)` → looks up `bindings.chats[chat_id]` → selects bot
- No match → uses `bindings.fallback_bot`
- If `fallback_bot` missing/invalid → falls back to `bots.default` (typically `"default"`)
- Each bot gets its own `FeishuClient` with its own `app_id`/`app_secret` credential pool
- V3.3.0 adds profile-aware routing: in multi-profile mode, selects the correct profile's bot credential pool based on `profile_id`
- `message.started` carries `chat_type`, `tenant_key`, `agent_id`, `profile_id` — currently passed through for future group filtering

## Requirements

- Python `3.9+`; Python `3.12` is recommended.
- Hermes Agent `v2026.4.23+`.
- macOS/Linux or another POSIX-like environment for sidecar process management and pidfiles.
- A Feishu/Lark custom app with permissions to send and update message cards.
- Python dependencies:
  - `aiohttp>=3.9`
  - `PyYAML>=6.0`

The installer checks `VERSION=v2026.4.23+` or Git tag `v2026.4.23+` in the Hermes directory, plus the `gateway/run.py` structure. If the check fails, it does not write Hermes files.

## Installation

For ordinary users, use the integrated `setup` installer. It creates a default config, validates credentials, checks Hermes compatibility, installs the hook, starts the sidecar, and verifies health.

```bash
git clone https://github.com/baileyh8/hermes-feishu-streaming-card.git
cd hermes-feishu-streaming-card
python3 -m pip install -e ".[test]"
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
python3 -m hermes_feishu_card.cli setup --hermes-dir ~/.hermes/hermes-agent --yes
```

By default, `setup` writes:

```text
~/.hermes_feishu_card/config.yaml
```

Use a custom config path when needed:

```bash
python3 -m hermes_feishu_card.cli setup \
  --hermes-dir ~/.hermes/hermes-agent \
  --config ~/.hermes_feishu_card/config.yaml \
  --yes
```

`setup` performs these steps:

1. Create a default config if it does not exist.
2. Verify Feishu credentials from environment variables or config.
3. Check the Hermes directory, version, and `gateway/run.py` structure.
4. Back up the original Hermes file and install the minimal hook.
5. Start the sidecar.
6. Call `/health` to confirm the sidecar is running.

If `FEISHU_APP_ID` or `FEISHU_APP_SECRET` is missing, `setup` stops before installing the hook. It only leaves the generated config file behind, preventing false-success installations that cannot send real Feishu cards.

Install the hook without starting the sidecar:

```bash
python3 -m hermes_feishu_card.cli setup --hermes-dir ~/.hermes/hermes-agent --skip-start --yes
```

### Advanced Troubleshooting Commands

Step-by-step commands remain available for diagnostics:

```bash
python3 -m hermes_feishu_card.cli doctor --config config.yaml.example --skip-hermes
python3 -m hermes_feishu_card.cli doctor --config config.yaml.example --hermes-dir ~/.hermes/hermes-agent
python3 -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes
python3 -m hermes_feishu_card.cli start --config config.yaml.example
python3 -m hermes_feishu_card.cli status --config config.yaml.example
```

`doctor` prints `version_source`, `version`, `minimum_supported_version`, `run_py_exists`, and the rejection reason. Confirm `doctor: ok` before manual installation.

Stop, restore, or uninstall:

```bash
python3 -m hermes_feishu_card.cli stop --config config.yaml.example
python3 -m hermes_feishu_card.cli restore --hermes-dir ~/.hermes/hermes-agent --yes
python3 -m hermes_feishu_card.cli uninstall --hermes-dir ~/.hermes/hermes-agent --yes
```

`restore` and `uninstall` use the installer backup and manifest. They refuse to overwrite files when the Hermes file, backup, or manifest has changed unexpectedly.

## Version Upgrade

### Upgrading From V3.2 To V3.3.0

V3.3.0 is backward compatible with V3.2's sidecar-only architecture. **Single-profile configurations work without any changes**; multi-profile features require config extension.

#### Upgrade Steps

1. **Back up current config**

   ```bash
   cp ~/.hermes_feishu_card/config.yaml ~/.hermes_feishu_card/config.yaml.v3.2.backup
   ```

2. **Stop the sidecar**

   ```bash
   python3 -m hermes_feishu_card.cli stop --config ~/.hermes_feishu_card/config.yaml
   ```

3. **Update code to V3.3.0**

   ```bash
   cd /path/to/hermes-feishu-streaming-card
   git checkout v3.3.0
   python3 -m pip install -e ".[test]" --upgrade
   ```

4. **Update config (for multi-profile)**

   Add a `profiles` section to `config.yaml` (see multi-profile config example below). Single-profile users need no changes.

5. **Restart sidecar**

   ```bash
   python3 -m hermes_feishu_card.cli start --config ~/.hermes_feishu_card/config.yaml
   python3 -m hermes_feishu_card.cli status --config ~/.hermes_feishu_card/config.yaml
   ```

#### Compatibility Notes

- V3.2 single-profile configs are **fully compatible** with V3.3.0
- Multi-profile is optional: without `profiles`, behavior is identical to V3.2
- Environment variables `FEISHU_APP_ID` / `FEISHU_APP_SECRET` are ignored in multi-profile mode (credentials come from each profile's config)
- To roll back: stop the sidecar, restore the backed-up `config.yaml`, and reinstall V3.2

## Configuration

Copy `config.yaml.example` to a local secure location and fill in credentials. Never commit real App Secrets to the repository.

### Single-profile Minimal Config

```yaml
server:
  host: 127.0.0.1
  port: 8765

feishu:
  app_id: ""
  app_secret: ""

card:
  title: Hermes Agent
  max_wait_ms: 800
  max_chars: 240
  footer_fields:
    - duration
    - model
    - input_tokens
    - output_tokens
    - context
```

### Single-profile + Multi-bot Config

```yaml
server:
  host: 127.0.0.1
  port: 8765

feishu:
  # Only used for fallback or single-bot mode
  app_id: ""
  app_secret: ""

bots:
  default: default
  items:
    sales:
      name: "Sales Group Bot"
      app_id: "cli_sales_xxx"
      app_secret: "xxx"
    support:
      name: "Support Bot"
      app_id: "cli_support_yyy"
      app_secret: "yyy"

bindings:
  fallback_bot: default
  chats:
    oc_5cc6a25d8815790fa890dd0226005e83: sales
    oc_7dd7b36e9826701fb901ee0337007f94: support
  group_rules:
    enabled: false

card:
  title: Hermes Agent
  max_wait_ms: 800
  max_chars: 240
  footer_fields:
    - duration
    - model
    - input_tokens
    - output_tokens
    - context
```

### Multi-profile Config (New in V3.3.0)

Multi-profile mode allows one sidecar to serve multiple Hermes profiles simultaneously, each with independent Feishu credentials, bot registrations, and routing bindings. Ideal for running multiple Hermes instances on a single machine.

```yaml
server:
  host: 127.0.0.1
  port: 8765

profiles:
  engineering:
    name: "Engineering"
    feishu:
      app_id: "cli_eng_xxx"
      app_secret: "eng_secret"
    bots:
      default: default
      items:
        default:
          name: "Engineering Bot"
          app_id: "cli_eng_xxx"
          app_secret: "eng_secret"
    bindings:
      fallback_bot: default
      chats: {}
  sales:
    name: "Sales"
    feishu:
      app_id: "cli_sales_xxx"
      app_secret: "sales_secret"
    bots:
      default: default
      items:
        default:
          name: "Sales Bot"
          app_id: "cli_sales_xxx"
          app_secret: "sales_secret"
        support:
          name: "Sales Support Bot"
          app_id: "cli_sales_support_yyy"
          app_secret: "support_secret"
    bindings:
      fallback_bot: default
      chats:
        oc_5cc6a25d8815790fa890dd0226005e83: support
  group_rules:
    enabled: false

card:
  title: Hermes Agent
  max_wait_ms: 800
  max_chars: 240
  footer_fields:
    - duration
    - model
    - input_tokens
    - output_tokens
    - context
```

> **Note**: In multi-profile mode, environment variables `FEISHU_APP_ID` / `FEISHU_APP_SECRET` are ignored. All credentials come from each profile's `feishu` sub-config. Each profile's `bots` and `bindings` fields default to built-in values if not explicitly set.

`card.title` controls the Feishu card header title. `footer_fields` controls which fields appear in the footer and their order; valid values are `duration`, `model`, `input_tokens`, `output_tokens`, `context`.

Default footer format:

```text
1m32s · MiniMax M2.7 · ↑1.1m · ↓2.2k · ctx 182k/204k 89%
```

Supported environment variables:

- `FEISHU_APP_ID` (single-profile mode)
- `FEISHU_APP_SECRET` (single-profile mode)
- `HERMES_FEISHU_CARD_HOST`
- `HERMES_FEISHU_CARD_PORT`
- `HERMES_FEISHU_CARD_ENABLED`
- `HERMES_FEISHU_CARD_EVENT_URL`
- `HERMES_FEISHU_CARD_TIMEOUT_MS`

## Feishu App Setup

Real card delivery requires a Feishu/Lark custom app. Prefer local config or environment variables:

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
```

Run a real Feishu smoke test:

```bash
FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=xxx \
python3 -m hermes_feishu_card.cli smoke-feishu-card --config config.yaml.example --chat-id oc_xxx
```

This command sends a test card and updates it once. It redacts App Secret, tenant token, and Authorization headers in output.

## Hermes Gateway Streaming And Thinking Configuration

This plugin renders events that Hermes already produces. It does not invent model thinking content. To see streaming thinking and progressive answers in the card, Hermes Gateway and the current model/provider must emit streaming events.

Check three things:

1. Hermes Gateway platform streaming is enabled: `streaming.enabled: true`, with `streaming.transport: edit`.
2. Feishu is not disabled by a platform override: avoid `display.platforms.feishu.streaming: false`; set it to `true` when you want to force Feishu streaming on.
3. The current model/provider supports and exposes reasoning/thinking deltas. If the model only returns a final answer, the card can only show the final answer.

In Hermes `config.yaml`, confirm the following. The common path is `~/.hermes/config.yaml`; if your config lives inside the Hermes installation directory, the installer also checks `<hermes-dir>/config.yaml`, `<hermes-dir>/config.yml`, `<hermes-dir>/configs/config.yaml`, and `<hermes-dir>/configs/config.yml`.

```yaml
streaming:
  enabled: true
  transport: edit
  # Optional. Hermes defaults are fine; these are the values used by the
  # locally verified real acceptance instance.
  edit_interval: 0.8
  buffer_threshold: 20
  cursor: ""
```

If your Hermes config previously disabled Feishu streaming with a platform override, explicitly enable it:

```yaml
display:
  platforms:
    feishu:
      streaming: true
```

Do not treat `display.show_reasoning` or `display.platforms.feishu.show_reasoning` as required for this plugin. In current Hermes source, those settings control Hermes' native final reasoning display and may prepend a `💭 Reasoning` code block to the final text, which can interfere with the card-only streaming experience. Enable them only when you intentionally want Hermes' native reasoning block in the final response.

`agent.reasoning_effort` is also optional and model/provider-dependent. It can affect whether some models produce reasoning, but it is not the Gateway card streaming switch.

How to read symptoms:

- The card is created, stays at "thinking", then completes: the model or Hermes probably did not emit thinking deltas.
- Answer text streams, but no thinking appears: streaming works, but the model is not exposing thinking.
- The card updates only once at the end: check `streaming.enabled`, `streaming.transport`, and `display.platforms.feishu.streaming`.
- No Feishu card appears: check Feishu credentials, sidecar status, and Hermes hook installation first.

`setup` and `doctor --hermes-dir` provide conservative Hermes config guidance. If common config files contain `streaming.enabled: false`, `streaming.transport: off`, or `display.platforms.feishu.streaming: false`, they print a warning. If Gateway streaming config cannot be detected, they print a note. This does not block installation because Hermes config schemas vary across versions.

## Architecture

```text
Hermes Gateway
  └─ minimal hook in gateway/run.py
       └─ hermes_feishu_card.hook_runtime
            └─ HTTP POST /events
                 └─ sidecar server
                      ├─ CardSession state machine
                      ├─ render_card() card rendering
                      ├─ FeishuClient tenant token / send / update
                      ├─ throttling, retry, locks, diagnostics
                      └─ /health metrics
```

The Hermes hook only converts the message lifecycle into `SidecarEvent` events:

- `message.started`
- `thinking.delta`
- `answer.delta`
- `tool.updated`
- `message.completed`
- `message.failed`

The sidecar owns complete session state and the Feishu CardKit boundary. This keeps Hermes code intrusion minimal while allowing card logic to be tested, restarted, and diagnosed independently.

Historical implementations are archived under `legacy/` for migration reference only and are not the active runtime. New development, tests, and installation entry points are under `hermes_feishu_card/`. See [docs/migration.en.md](docs/migration.en.md).

## Diagnostics

`/health` and `status` expose process-local metrics:

- `events_received`
- `events_applied`
- `events_ignored`
- `events_rejected`
- `feishu_send_successes`
- `feishu_send_failures`
- `feishu_update_successes`
- `feishu_update_failures`
- `feishu_update_retries`

`stop` validates the PID/token in the pidfile against `process_pid`/`process_token` from `/health` before stopping a process, preventing stale pidfiles or PID reuse from killing unrelated services.

Card creation is not retried automatically, avoiding duplicate cards when the response is ambiguous. Updates for known message IDs use a limited retry.

## Troubleshooting

### `doctor` says Hermes is unsupported

Confirm the Hermes version is at least `v2026.4.23` and that the target directory contains `gateway/run.py`. The installer reads `VERSION` or Git tags; inspect `version_source`, `version`, and `reason` if detection fails.

### The sidecar starts but no real card appears

Check `FEISHU_APP_ID` and `FEISHU_APP_SECRET` (in multi-profile mode, check each profile's `feishu` config). Without credentials, the sidecar uses a no-op client that accepts events but does not send real Feishu cards.

### The card has no thinking content or does not stream

Check Hermes `config.yaml` for `streaming.enabled: true` and `streaming.transport: edit`. If `display.platforms.feishu.streaming: false` is present, remove that override or set it to `true`. Then confirm that the current model/provider actually exposes reasoning/thinking deltas. Do not blindly enable `show_reasoning` for card thinking; it may only append a final reasoning code block to Hermes' native response. The plugin config file `~/.hermes_feishu_card/config.yaml` only controls card title, footer, throttling, and rendering options. It does not control whether Hermes Gateway emits `thinking.delta` or `answer.delta`.

### Duplicate cards appear

Check `feishu_send_successes`, `events_received`, and `events_rejected` in `/health`. V3.3.0 uses a per-message lock and message_id mapping; in multi-profile mode, `profile_id:message_id` composite keys provide isolation. One Hermes message should create one Feishu card.

### Gray native text appears

Check whether the sidecar received and applied `message.completed`. After the sidecar accepts the completion event, the Hermes hook suppresses duplicate native text. If the sidecar is unavailable, the hook fails open and Hermes native text continues. V3.3.0 fixes the issue where the complete hook swallowed responses on non-Feishu platforms.

### Footer token numbers look wrong

V3.3.0 filters obviously abnormal token totals. If the footer still looks wrong, inspect the `tokens` and `context` metadata passed by Hermes Gateway.

### Restore fails

`restore` refuses to overwrite files when Hermes files or backups changed after installation. Back up the current Hermes directory, then inspect `gateway/run.py`, the backup, and the manifest before restoring manually.

### Multi-profile config not working

Ensure `profiles` is correctly defined in `config.yaml` and each profile's `feishu.app_id`/`feishu.app_secret` is set. Environment variables `FEISHU_APP_ID`/`FEISHU_APP_SECRET` are ignored in multi-profile mode. Check sidecar startup logs for profile loading confirmation.

### Card table limit exceeded

Feishu CardKit enforces a strict limit: **maximum 5 table components per card** (per language if multi-language is configured). V3.3.0 includes built-in table limit protection — tables exceeding the limit are automatically truncated with a notice appended. To keep all tables, reduce the number of Markdown tables in your content.

## Testing

Full local test suite:

```bash
python3 -m pytest -q
```

Focused checks:

```bash
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration -q
python3 -m pytest tests/unit/test_docs.py -q
python3 -m pytest tests/integration/test_feishu_client_http.py -q
```

Current V3.3.0 acceptance status:

- Full automated test suite: **425 passed, 0 failed**
- GitHub Actions: Python 3.9 / 3.12 matrix passed
- Installer/restore tests cover backups, manifest, duplicate install, modified-file refusal, uninstall, and restore idempotency
- Real Hermes Gateway E2E verified card creation, streaming updates, tool counts, completion state, and footer metadata
- Real Feishu app verified in-card updates with no duplicate gray native messages
- Real long-card stress test updated one Feishu card to 16k Chinese characters
- Fresh Hermes `v2026.4.23`: `doctor → install → doctor → restore → doctor` loop completed
- Ordinary-user `setup --hermes-dir ... --yes` covers config creation, hook install, sidecar startup, and health check
- V3.3.0 multi-profile routing verified: `engineering` / `sales` profiles with independent credentials and session isolation
- V3.3.0 DeepSeek compatibility: `<thinking>` tag filtering verified by unit tests
- V3.3.0 table protection: truncation logic verified by unit tests

## Version History

| Version | Date | Highlights |
|---------|------|-----------|
| [v3.3.0](https://github.com/baileyh8/hermes-feishu-streaming-card/releases/tag/v3.3.0) | 2026-05-01 | Multi-profile support, DeepSeek compatibility, table protection, footer spinner, platform check fix |
| [v3.2.1](https://github.com/baileyh8/hermes-feishu-streaming-card/releases/tag/v3.2.1) | 2026-04-29 | HTTP Accept-Encoding fix (brotli compatibility) |
| [v3.2.0](https://github.com/baileyh8/hermes-feishu-streaming-card/releases/tag/v3.2.0) | 2026-04-29 | Multi-bot registry & routing, chat bindings, Bot CLI, routing diagnostics |
| [v3.1.0](https://github.com/baileyh8/hermes-feishu-streaming-card/releases/tag/v3.1.0) | 2026-04 | Sidecar architecture, streaming card updates, health endpoint, auto-recovery, install wizard |
| [v3.0.0](https://github.com/baileyh8/hermes-feishu-streaming-card/releases/tag/v3.0.0) | 2026-04 | Initial sidecar-only architecture release (migrated from V2.x monolith hook) |

Full changelog: [CHANGELOG.md](CHANGELOG.md).

## Documentation

- Architecture: [中文](docs/architecture.md) / [English](docs/architecture.en.md)
- Event protocol: [中文](docs/event-protocol.md) / [English](docs/event-protocol.en.md)
- Installer safety: [中文](docs/installer-safety.md) / [English](docs/installer-safety.en.md)
- Migration: [中文](docs/migration.md) / [English](docs/migration.en.md)
- E2E verification: [中文](docs/e2e-verification.md) / [English](docs/e2e-verification.en.md)
- Release readiness: [中文](docs/release-readiness.md) / [English](docs/release-readiness.en.md)
- Testing: [中文](docs/testing.md) / [English](docs/testing.en.md)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Security

Do not commit App Secret, tenant token, real chat_id, or private conversation content to the repository. The README images are only public demonstrations of the V3.3.0 card experience. Production credentials should always live in local config, environment variables, or a dedicated secret manager.
