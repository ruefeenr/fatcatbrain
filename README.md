# fatcatbrain

A playful local context-capture CLI companion for AI project work. A fat cat mascot
sniffs out useful context from your brain dumps, proposes memory candidates, and only
stores what you confirm.

The technical core is this loop:

```text
Input -> extract candidates -> Memory Inbox -> you confirm/edit -> store memory -> export context
```

## Status

MVP, phases 1-3:

- Project skeleton, hexagonal architecture (domain / application / adapters)
- JSONL/JSON file storage
- FakeLLM adapter (deterministic, for the core loop without a server)
- Ollama adapter (real candidate extraction)
- CLI commands: `init`, `save`, `brain`, `import`, `inbox`, `memories`

Not in scope yet: full project management, quiz/game mode, rich context-pack export,
SQLite, vector DB, voice/Whisper, OpenAI adapter, Textual TUI.

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)
- Optional: a running [Ollama](https://ollama.com) server for real extraction

## Setup

```bash
uv sync
```

## Usage

```bash
uv run fcb init                       # interactive setup: choose how the cat thinks
uv run fcb init --reconfigure         # run the LLM setup again
uv run fcb save "I prefer FastAPI for small APIs."
uv run fcb brain                      # type line by line, finish with an empty line
uv run fcb brain --editor             # compose the dump in your $EDITOR
uv run fcb brain --stdin              # paste a block, finish with CTRL+D
echo "..." | uv run fcb brain         # piped input is read directly
uv run fcb import notes.txt           # import a file as a brain dump
uv run fcb inbox                      # review candidates: (s)ave (e)dit (p)roject (d)iscard
uv run fcb memories                   # list confirmed memory items
```

## Choosing an LLM

Run `fcb init` and the cat asks how it should think. It detects your local
[Ollama](https://ollama.com) install, lists the models you have, and lets you pick
one (cloud APIs are coming later). The choice is saved to `config.json`.

Recommended local models for memory extraction (good JSON / instruction following):

- `gpt-oss:20b` - strong quality if your hardware allows
- `qwen2.5:7b` / `qwen2.5:14b` - excellent and lightweight
- `llama3.1:8b` - solid, fast fallback

Pull one with e.g. `ollama pull qwen2.5`. You can also override the choice per-run
with environment variables (these take precedence over `config.json`):

```bash
FCB_LLM=ollama FCB_OLLAMA_MODEL=gpt-oss:20b uv run fcb brain
```

Configuration precedence is: environment variables > `config.json` > defaults.

## Passive capture (listen mode)

Instead of actively dumping thoughts, let the cat read your AI chat transcripts and
distill the essence into the inbox. It reads only *your* messages, keeps just the
gist as candidates, stores **no raw text**, and still requires review before
anything becomes a memory.

```bash
# Watch the current project's Cursor transcripts (auto-detected, no --dir needed)
uv run fcb listen

# Or point --dir at a specific agent-transcripts folder
uv run fcb listen --dir ~/.cursor/projects/<your-project>/agent-transcripts

# Process the current backlog once and exit (good for testing / cron)
uv run fcb listen --once

# Run in the background and free your terminal, then review in another shell
uv run fcb listen --daemon
uv run fcb listen --status
uv run fcb listen --stop
```

Notes:
- `fcb listen` auto-detects the current project's Cursor transcript folder; review
  candidates from another terminal with `fcb inbox` (the foreground listener keeps
  the terminal busy, or use `--daemon`).
- Use Ollama for real "essence" extraction; the FakeLLM adapter just splits
  sentences and is noisy.
- Only new messages are processed on each poll; progress is tracked in
  `$FCB_HOME/watch_state.json`.
- `FCB_MIN_CONFIDENCE` (default 0.6) drops low-confidence noise.
- This is opt-in and local only. There is no global keystroke capture by design.

## Configuration (environment variables)

| Variable           | Default            | Meaning                                  |
| ------------------ | ------------------ | ---------------------------------------- |
| `FCB_HOME`         | `~/.fatcatbrain`   | Storage root directory                   |
| `FCB_LLM`          | `fake`             | LLM adapter: `fake` or `ollama` (overrides config.json) |
| `FCB_OLLAMA_MODEL` | `llama3.1`         | Ollama model name (overrides config.json) |
| `FCB_OLLAMA_HOST`  | (ollama default)   | Ollama host URL                          |
| `FCB_TRANSCRIPTS_DIR` | (none)          | Directory watched by `fcb listen`        |
| `FCB_MIN_CONFIDENCE`  | `0.6`           | Min candidate confidence in listen mode  |
| `FCB_LISTEN_INTERVAL` | `10`            | Seconds between polls in listen mode      |

## Storage layout

```text
$FCB_HOME/
  config.json
  watch_state.json        # listen-mode progress per transcript file
  projects/
    default/
      project.json
      raw_inputs.jsonl
      inbox.jsonl
      memory_items.jsonl
```

## Architecture

Hexagonal, but deliberately lightweight. The domain knows nothing about the CLI,
Ollama, or JSON files. Use-cases talk only to ports (`typing.Protocol`); adapters
implement those ports; everything is wired together in `composition.py`.

```text
src/fatcatbrain/
  domain/        # pure models, value objects, policies
  application/   # ports (interfaces) + use cases
  adapters/      # cli, llm, persistence, ingest
  config/        # settings
  composition.py # composition root
```

## Tests

```bash
uv run pytest
```
