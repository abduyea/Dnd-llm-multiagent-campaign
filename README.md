````markdown
# D&D Multi-AI Agent Storytelling System

## CSB 440 Capstone Project — Spring 2026

### Team DS_ams
- Spencer K
- Abdulfetah Adem
- Mizpah Parilla

---

# Project Overview

The D&D Multi-AI Agent Storytelling System is a browser-based tabletop RPG platform powered by multiple AI agents, persistent memory systems, and rule-based gameplay mechanics.

The system combines:
- AI-driven narration
- Autonomous character interaction
- Persistent campaign memory
- Rule validation
- Browser-based gameplay

The platform delivers immersive Dungeons & Dragons storytelling experiences using local Large Language Models (LLMs) and a multi-agent architecture.

---

# Core Features

## Campaign Management
Create and manage Dungeons & Dragons campaigns through a browser interface.

## Character System
Supports character creation, progression, inventory management, and gameplay interaction.

## AI Dungeon Master
An AI Dungeon Master dynamically narrates the world and responds to player actions.

## NPC Interaction
AI-powered NPC dialogue and contextual interactions.

## Persistent Memory
Stores session history, character states, and narrative continuity across campaigns.

## Rule Validation
Deterministic gameplay mechanics ensure consistent rule-based interactions.

## Multi-Agent Architecture
Specialized AI agents handle narration, dialogue, gameplay logic, and memory processing.

---

# Technologies Used

## Backend
- Python
- FastAPI
- Uvicorn

## Frontend
- HTML
- CSS
- Vanilla JavaScript
- Bootstrap

## AI / LLM
- Ollama
- Llama Models
- Qwen Models

## Database
- SQLite

## Infrastructure
- Docker
- Docker Compose

## Development Tools
- GitHub
- pytest
- Alembic

---

# System Architecture

The application uses a multi-layer architecture:

## Frontend Layer
Provides:
- Campaign management
- Character creation
- Gameplay interaction
- Real-time storytelling interface

## Backend Layer
Handles:
- Gameplay logic
- Rule validation
- Session management
- API communication
- Memory processing

## AI Agent Layer
Includes:
- Dungeon Master Agent
- Character Agents
- NPC Agents
- Summarizer Agent

## Persistent Memory Layer
Stores:
- Campaign history
- Character states
- Narrative events
- Session progression

---

# How to Run the Application (Manual Setup)

## STEP 1 — Open PowerShell and Go to Project Folder

```powershell
cd C:\Users\abduy\Dnd-llm-multiagent-campaign
````

Check current folder:

```powershell
pwd
```

## STEP 2 — Create the `.env` File

Run:

```powershell
Copy-Item .env.example .env
```

Check the file:

```powershell
dir .env
```

Expected:

* `.env` file appears

## STEP 3 — Install Project Dependencies

Run:

```powershell
uv sync --extra dev
```

Expected:

* Packages install successfully

## STEP 4 — Set Up the Database

Run:

```powershell
uv run alembic upgrade head
```

Possible message:

```text
table campaigns already exists
```

Meaning:

* The database was already initialized previously.
* This is okay.

## STEP 5 — Start Ollama

Open a new PowerShell terminal.

Run:

```powershell
ollama serve
```

Expected:

* Ollama server starts successfully

Leave this terminal open.

## STEP 6 — Download the AI Model

Open another terminal.

Run:

```powershell
ollama pull llama3.2:3b
```

Expected:

* Model downloads successfully

## STEP 7 — Start the Backend Server

Go back to the project folder terminal.

Run:

```powershell
uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected:

```text
Uvicorn running on http://0.0.0.0:8000
```

Meaning:

* Backend API server is running successfully.

Leave this terminal open.

## STEP 8 — Start the Frontend Server

Open another terminal.

Go to the project folder:

```powershell
cd C:\Users\abduy\Dnd-llm-multiagent-campaign
```

Run:

```powershell
python -m http.server 3000 --directory frontend
```

Expected:

```text
Serving HTTP on ...
```

Meaning:

* Frontend server is running successfully.

Leave this terminal open.

## STEP 9 — Open the Application

Open browser and go to:

```text
http://localhost:3000
```

Expected:

* D&D Storyteller application opens

Top-right status should display:

```text
BACKEND OK · AI READY
```

Meaning:

* Frontend
* Backend
* Database
* AI model

are all working correctly.

# Terminals Used

## Terminal 1

```powershell
ollama serve
```

## Terminal 2

Backend server:

```powershell
uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Terminal 3

Frontend server:

```powershell
python -m http.server 3000 --directory frontend
```

# How to Stop the Application

Press:

```text
Ctrl + C
```

inside each running terminal.

# Current Project Status

The application currently supports:

* Campaign management
* Character interaction
* AI narration
* Persistent memory
* Gameplay actions
* Session tracking
* Rule validation

The system successfully integrates:

* Frontend
* Backend
* AI agents
* Database
* Persistent storytelling workflows

# Future Improvements

## Multiplayer Support

Add synchronized multiplayer gameplay.

## Visual Gameplay Features

Interactive maps and token systems.

## Advanced Spell System

Expanded combat and spell mechanics.

## Authentication

User accounts and secure login system.

## Enhanced Memory Systems

Improved long-term narrative tracking.

## Cloud Deployment

Cloud scalability and remote accessibility.

# GitHub Repository

```text
https://github.com/abduyea/Dnd-llm-multiagent-campaign.git
```

# Confluence Documentation

```text
https://seattlecolleges-team-yellow-spring26.atlassian.net/wiki/x/H4CN
```

# Project Summary

The D&D Multi-AI Agent Storytelling System demonstrates how AI-driven narration, persistent memory, and rule-based gameplay mechanics can be integrated into an immersive tabletop RPG experience.

This capstone project combines:

* Frontend interaction
* Backend processing
* Multi-agent AI systems
* Persistent storytelling workflows

into a functional browser-based storytelling platform.

The project establishes a scalable foundation for adaptive storytelling, intelligent campaign management, and autonomous character interaction for modern Dungeons & Dragons gameplay experiences.

```

```
