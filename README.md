# fatcatbrain

```text
                      _
            __       / |
            \ "-..--'_4|_
 _._____     \ _  _(C "._'._
((^     '"-._( O_ O "._` '. \
 `"'--._     \  y_     \   \|
        '-._  \_ _  __.=-.__,\_
            `'-(" ,("___       \,_____
                (_,("___     .-./     '
                |   C'___    (5)
                /    ``  '---'-'._```
               |     ```    |`    '"-._
               |    ````    \-.`
               |    ````    |  "._ ``
               /    ````    |     '-.__
              |     ```     |
              |     ```     |
              |     ```     |
              |     ```     /
              |    ````    |
              |    ```     |
              |    ```     /
              |    ```     |
              /    ```     |
             |     ```     |
             |     ```     !
             |     ```    / '-.___
             |    ````    !_      ''-
             /   `   `    | '--._____)
             |     /|     !
             !    / |     /
             |    | |    /
             |    | |   /
             |    / |   |
             /   /  |   |
            /   /   |   |
           (,,_]    (,_,)
```

```text
Input -> extract candidates -> Memory Inbox -> you confirm/edit -> store memory -> export context
```

## Status

MVP, phases 1-3:

- Project skeleton, hexagonal architecture (domain / application / adapters)
- JSONL/JSON file storage
- FakeLLM adapter (deterministic, for the core loop without a server)
- Ollama adapter (real candidate extraction)
- Passive capture from chat transcripts (`listen`, `import-chat`)
- Auto-detected projects with global vs project-scoped memories
- CLI commands: `init`, `save`, `brain`, `import`, `import-chat`, `listen`,
  `inbox`, `memories`

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

```text
 /ᐠ｡ꞈ｡ᐟ\   "Dump your thoughts, I'll sniff out the useful bits."
```

```bash
uv run fcb init                       # interactive setup: choose how the cat thinks
uv run fcb init --reconfigure         # run the LLM setup again
uv run fcb save "I prefer FastAPI for small APIs."
uv run fcb save "Alpha uses Postgres." -p   # scope to the auto-detected project
uv run fcb brain                      # type line by line, finish with an empty line
uv run fcb brain --editor             # compose the dump in your $EDITOR
uv run fcb brain --stdin              # paste a block, finish with CTRL+D
echo "..." | uv run fcb brain         # piped input is read directly
uv run fcb import notes.txt           # import a file as a brain dump
uv run fcb import-chat                 # distill an existing chat history
uv run fcb listen                     # passively listen to chat transcripts
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

```text
 /ᐠ•ꞈ•ᐟ\   "Ears up. I'm listening while you work."
```

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
  watch_state.json          # listen-mode progress per transcript file
  global/
    memory_items.jsonl      # global memories, visible from every project
  projects/
    <project-id>/           # auto-detected from the working directory
      project.json
      raw_inputs.jsonl
      inbox.jsonl
      memory_items.jsonl    # this project's memories
```

The active project is auto-detected from your working directory (the git root's
folder name), unless you override it with `FCB_PROJECT`. Global memories (`fcb save`
without `-p`) follow you everywhere; project-scoped ones (`-p`) stay put.

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

## The cat's moods

The mascot changes face with the situation, so the CLI feels alive:

```text
 /ᐠ｡ꞈ｡ᐟ\    curious   — sniffing, found something, project detected
 /ᐠ•ꞈ•ᐟ\    working   — thinking / listening
 /ᐠ≽^•⩊•^≼マ  happy     — saved, all good
 /ᐠಠ_ಠᐟ\    suspicious — sensitive, needs review, or something's off
 /ᐠ - ˕ -マ   sleepy    — idle, nothing to do, nap time
```

## Tests

```bash
uv run pytest
```

```text
 /ᐠ≽^•⩊•^≼マ  "All green? Time for a nap."
```
