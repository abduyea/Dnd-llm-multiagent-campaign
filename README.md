# D&D Multi-AI Agent Storytelling System

A local AI-powered Dungeons & Dragons web app — no cloud required.

![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green?style=flat-square)
![Ollama](https://img.shields.io/badge/AI-Ollama_Local-orange?style=flat-square)
![Tests](https://img.shields.io/badge/Tests-387_passing-brightgreen?style=flat-square)
![License](https://img.shields.io/badge/License-Academic%20%2F%20Educational-purple?style=flat-square)

## Requirements

- [Python 3.12+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- [Ollama](https://ollama.com/)

## How to Run

> Open **three terminal windows** in the project folder.

**1. Install dependencies**

```bash
uv sync --extra dev
```

**2. Create config file**

```bash
# macOS / Linux
cp .env.example .env

# Windows
copy .env.example .env
```

**3. Set up the database**

```bash
uv run alembic upgrade head
```

**4. Download an AI model**

```bash
ollama pull llama3.2:3b
```

**5. Start Ollama** — Terminal 1

```bash
ollama serve
```

**6. Start the backend** — Terminal 2

```bash
uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

**7. Start the frontend** — Terminal 3

```bash
python -m http.server 3000 --directory frontend
```

**8. Open in browser**

```
http://localhost:3000
```

## Demo

1. Go to `http://localhost:3000`
2. Click **"Quick Start — The Sunken Vault"**

Loads a pre-built campaign with two characters ready to play.

## Docker

```bash
docker compose up --build
```

Pull models on first run:

```bash
docker compose --profile init run pull-models
```

| Service | URL                   |
| :------ | :-------------------- |
| App     | http://localhost:8081 |
| API     | http://localhost:8000 |

---

## Tests

```bash
uv run pytest tests/ -v
```

---

## Troubleshooting

| Problem              | Fix                                                                              |
| :------------------- | :------------------------------------------------------------------------------- |
| Backend won't start  | Run `uv run alembic upgrade head` first                                        |
| Ollama unavailable   | Run `ollama serve` in a separate terminal                                      |
| AI using static text | Run `ollama pull llama3.2:3b` then `ollama list`                             |
| Port in use          | Change port in uvicorn command and update `API_BASE` in `frontend/js/api.js` |

---

Academic / Educational Use — [@abduyea](https://github.com/abduyea)
