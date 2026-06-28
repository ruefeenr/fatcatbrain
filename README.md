# fatcat
## Usage

```text
 /ᐠ｡ꞈ｡ᐟ\   "Dump your thoughts, I'll sniff out the useful bits."
```

```bash
uv run fcat -h                         # show every available command
uv run fcat init                       # interactive setup: choose how the cat thinks
uv run fcat start                      # detect Cursor/Codex and learn in background
uv run fcat review                     # review learnings in plain language
uv run fcat show                       # see what FatCat knows and is still learning
uv run fcat stop                       # stop background learning
uv run fcat init --reconfigure         # run the LLM setup again
uv run fcat save "I prefer FastAPI for small APIs."
uv run fcat save "Alpha uses Postgres." -p   # scope to the auto-detected project
uv run fcat brain                      # type line by line, finish with an empty line
uv run fcat brain --editor             # compose the dump in your $EDITOR
uv run fcat brain --stdin              # paste a block, finish with CTRL+D
echo "..." | uv run fcat brain         # piped input is read directly
uv run fcat import notes.txt           # import a file as a brain dump
uv run fcat import-chat                 # distill an existing chat history
uv run fcat import-codex                # detect and import the latest Codex session
uv run fcat listen                     # passively listen to chat transcripts
uv run fcat listen --source codex -p   # follow the latest active Codex session
uv run fcat inbox                      # review memory and learning-issue proposals
uv run fcat review                     # review the latest unreviewed session
uv run fcat sessions                   # list capture sessions
uv run fcat inbox --deferred           # revisit issues put aside for later
uv run fcat memories                   # list confirmed memory items
uv run fcat issues                     # list confirmed learning questions
uv run fcat reset                      # selectively clear local FatCat data
```

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
Input -> memory proposals + learning questions -> you review -> confirmed knowledge
```

A FatCat learning issue is not a project backlog item. It is an unanswered,
reusable question about the user's preferences, decision policy, constraints,
rationale, or working style. The project records where that question surfaced;
the issue scope records where its eventual answer is expected to apply.

## Status

MVP, phases 1-3:

- Project skeleton, hexagonal architecture (domain / application / adapters)
- JSONL/JSON file storage
- Ollama adapter using `gpt-oss:20b` for candidate extraction
- User-curated learning questions with confirm/edit/merge/reject/defer workflow
- Evidence quotes, importance, keywords, and session-ready metadata
- Passive capture from chat transcripts (`listen`, `import-chat`)
- Auto-detected projects with global vs project-scoped memories
- CLI commands: `init`, `save`, `brain`, `import`, `import-chat`,
  `import-codex`, `listen`, `inbox`, `review`, `sessions`, `memories`,
  `issues`, `reset`

Not in scope yet: full project management, quiz/game mode, rich context-pack export,
SQLite, vector DB, voice/Whisper, OpenAI adapter, Textual TUI.

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)
- A running [Ollama](https://ollama.com) server
- The `gpt-oss:20b` model installed in Ollama

## Setup

```bash
uv sync
```

## LLM setup

Run `fcat init` and the cat asks how it should think. It detects your local
[Ollama](https://ollama.com) install, lists the models you have, and lets you pick
`gpt-oss:20b`. The choice is saved to `config.json`.

Install and start the model with:

```bash
ollama serve
ollama pull gpt-oss:20b
```

You can override the Ollama host or model per run with environment variables:

```bash
FATCAT_LLM=ollama FATCAT_OLLAMA_MODEL=gpt-oss:20b uv run fcat brain
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
uv run fcat listen

# Or bind to the latest active Codex session
uv run fcat listen --source codex --project

# Or point --dir at a specific agent-transcripts folder
uv run fcat listen --dir ~/.cursor/projects/<your-project>/agent-transcripts

# Process the current backlog once and exit (good for testing / cron)
uv run fcat listen --once

# Run in the background and free your terminal, then review in another shell
uv run fcat listen --daemon
uv run fcat listen --status
uv run fcat listen --stop
```

Notes:
- A Codex listener binds to the latest active session at startup and does not jump
  to another thread while running.
- `fcat listen` auto-detects the current project's Cursor transcript folder; review
  candidates from another terminal with `fcat review` (the foreground listener keeps
  the terminal busy, or use `--daemon`).
- Candidate extraction always uses Ollama; there is no heuristic runtime fallback.
- Only new messages are processed on each poll; progress is tracked in
  `$FATCAT_HOME/watch_state.json`.
- `FATCAT_MIN_CONFIDENCE` (default 0.6) drops low-confidence noise.
- This is opt-in and local only. There is no global keystroke capture by design.

## Codex sessions

`fcat import-codex` detects the most recently active local Codex thread, shows
its title for confirmation, and imports only real user messages. Generated
environment context, assistant responses, and tool logs are ignored. The import
is stored as a FatCat session and can be curated with:

```bash
fcat review
fcat sessions
```

## Configuration (environment variables)

| Variable           | Default            | Meaning                                  |
| ------------------ | ------------------ | ---------------------------------------- |
| `FATCAT_HOME`         | `~/.fatcat`   | Storage root directory                   |
| `FATCAT_LLM`          | `ollama`           | LLM adapter (currently Ollama) |
| `FATCAT_OLLAMA_MODEL` | `gpt-oss:20b`      | Ollama model name (overrides config.json) |
| `FATCAT_OLLAMA_HOST`  | (ollama default)   | Ollama host URL                          |
| `FATCAT_TRANSCRIPTS_DIR` | (none)          | Directory watched by `fcat listen`        |
| `FATCAT_MIN_CONFIDENCE`  | `0.6`           | Min candidate confidence in listen mode  |
| `FATCAT_LISTEN_INTERVAL` | `10`            | Seconds between polls in listen mode      |

## Storage layout

```text
$FATCAT_HOME/
  config.json
  watch_state.json          # listen-mode progress per transcript file
  global/
    memory_items.jsonl      # global memories, visible from every project
    issues.jsonl            # confirmed non-project issues
  projects/
    <project-id>/           # auto-detected from the working directory
      project.json
      raw_inputs.jsonl
      inbox.jsonl
      issue_inbox.jsonl
      issues.jsonl
      sessions.jsonl
      memory_items.jsonl    # this project's memories
```

The active project is auto-detected from your working directory (the git root's
folder name), unless you override it with `FATCAT_PROJECT`. Global memories (`fcat save`
without `-p`) follow you everywhere; project-scoped ones (`-p`) stay put.

## Architecture

Hexagonal, but deliberately lightweight. The domain knows nothing about the CLI,
Ollama, or JSON files. Use-cases talk only to ports (`typing.Protocol`); adapters
implement those ports; everything is wired together in `composition.py`.

```text
src/fatcat/
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
