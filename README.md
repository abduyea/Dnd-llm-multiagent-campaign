# D&D Storyteller

A local web app for running D&D-style campaigns with AI narration.

## Features

- Create campaigns and characters
- Start and manage game sessions
- Roll dice and resolve combat actions
- Stream AI narration in the browser
- Save campaign and session data locally

## Tech Stack

- Python 3.12
- FastAPI
- SQLite
- SQLAlchemy
- Alembic
- Ollama
- Vanilla JavaScript
- Bootstrap
- Docker

## Installation

1. Install Python 3.12 or newer.

2. Install `uv`.

```bash
pip install uv
```

3. Install project dependencies.

```bash
uv sync --extra dev
```

4. Create a local environment file.

```bash
copy .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

5. Set up the database.

```bash
uv run alembic upgrade head
```

6. Start Ollama in a separate terminal.

```bash
ollama serve
```

7. Download the local AI model.

```bash
ollama pull llama3.2:3b
```

8. Start the backend.

```bash
uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

9. Start the frontend.

```bash
python -m http.server 3000 --directory frontend
```

10. Open the app.

```text
http://localhost:3000
```

## How to Use

Open the app in your browser. Create a campaign, add characters, start a session, and enter player actions. The backend handles dice, game state, and narration.

## Project Structure

```text
backend/      FastAPI backend
frontend/     Browser frontend
tests/        Test suite
data/         Local database folder
V2/           Previous version kept for reference
```

## Environment Variables

Create `.env` from `.env.example`.

```env
DATABASE_URL=sqlite+aiosqlite:///./data/dnd.db
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT=8
```

## Notes

- Ollama must be running before using AI narration.
- The local database is stored in `data/dnd.db`.
- Runtime files and caches are ignored by Git.

## License

This project is licensed under the MIT License.
