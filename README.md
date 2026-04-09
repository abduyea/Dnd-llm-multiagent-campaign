# 🎲 D&D LLM Campaign

### Multi-Agent AI Storytelling System

## 🚀 Project Status

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![Streamlit](https://img.shields.io/badge/Streamlit-Frontend-red)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20%7C%20LLaMA-purple)
![VectorDB](https://img.shields.io/badge/VectorDB-FAISS%20%7C%20Chroma-orange)
![Status](https://img.shields.io/badge/Status-In%20Development-yellow)
![License](https://img.shields.io/badge/License-Academic-lightgrey)

## 📌 Overview

A **multi-agent AI storytelling system** that simulates a full Dungeons & Dragons campaign using Large Language Models.

Instead of a human Dungeon Master, the system orchestrates:

* Narrative generation
* Character decision-making
* Rule enforcement
* Persistent world memory

📍 Problem Solved:
Traditional D&D depends on human DMs and inconsistent storytelling. This system creates a **scalable, intelligent, and structured AI-driven gameplay experience**

## 🎯 Objective

Deliver a **web-based, fully functional prototype** that enables:

* Multi-agent gameplay (DM + characters)
* Persistent memory across sessions
* Real-time narrative generation
* Structured and consistent storytelling

## 🧠 System Architecture

### 🔷 High-Level Architecture Diagram

```mermaid
flowchart TD
    A[User Interface\n(Streamlit / React)]
    B[Backend API\n(FastAPI)]
    C[Multi-Agent System]
    D1[DM Agent]
    D2[Character Agents]
    E[Memory System]
    F[Vector DB\n(FAISS / Chroma)]
    G[Persistent Storage\n(JSON / Logs)]

    A --> B
    B --> C
    C --> D1
    C --> D2
    C --> E
    E --> F
    F --> G
```

### 🧩 Architecture Explanation

| Layer                  | Responsibility                   |
| ---------------------- | -------------------------------- |
| **Frontend**     | User interaction & visualization |
| **Backend API**  | Orchestration & request handling |
| **Agents**       | DM + character intelligence      |
| **Memory Layer** | Context persistence              |
| **Vector DB**    | Semantic retrieval               |
| **Storage**      | Logs & campaign state            |

📌 This modular architecture ensures:

* Scalability
* Maintainability
* High performance

## ⚙️ Core Features

### 🤖 Multi-Agent System

* Dungeon Master (DM) agent
* 3–4 autonomous character agents

### 🎲 Gameplay Engine

* Turn-based interaction loop
* Dice roll simulation
* Structured JSON outputs

### 🧠 Memory System

* Shared campaign memory
* Private agent memory
* Retrieval-Augmented Generation (RAG)

### 📊 Character Management

* HP tracking
* Inventory system
* Ability updates

### 📏 Rule Enforcement

* Action validation
* Consistency checks
* Contradiction detection

### 🧾 Session System

* Save / Load campaigns
* Logging
* Recap generation

## 🧪 Tech Stack

```text
Backend        → FastAPI
Frontend       → Streamlit / React
LLM            → OpenAI / LLaMA
Vector DB      → FAISS / Chroma
Data Format    → JSON
Deployment     → Docker (planned)
```

## 📂 Project Structure

```bash
dnd-llm-campaign/
│
├── data/
│   ├── logs/
│   ├── memory/
│   └── characters/
│
├── src/
│   ├── agents/
│   ├── engine/
│   ├── memory/
│   ├── api/
│   └── utils/
│
├── frontend/
├── notebooks/
├── tests/
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env
└── README.md
```

## ⚡ Quick Start (Local Setup)

### 1️⃣ Clone Repository

```bash
git clone https://github.com/your-repo/dnd-llm-campaign.git
cd dnd-llm-campaign
```

### 2️⃣ Create Environment

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3️⃣ Set Environment Variables

Create `.env` file:

```env
OPENAI_API_KEY=your_key_here
VECTOR_DB=faiss
```

### 4️⃣ Run Backend

```bash
uvicorn src.api.main:app --reload
```

### 5️⃣ Run Frontend

```bash
streamlit run frontend/app.py
```

## 🐳 Docker Setup (Production Ready)

### Build Image

```bash
docker build -t dnd-llm .
```

### Run Container

```bash
docker run -p 8000:8000 dnd-llm
```

📌 Why Docker?

* Ensures consistent environment
* Eliminates dependency issues
* Enables easy deployment

## 📊 Success Metrics

### Technical

* Multi-agent system runs end-to-end
* Memory recall ≥ 90%
* Response time < 3 seconds

### Product

* Session duration ≥ 10 minutes
* Coherent storytelling

### Academic

* Complete documentation
* Reproducibility

## 🔬 Research Questions

This project explores:

* Multi-agent vs single-agent performance
* Impact of memory on narrative continuity
* Rule enforcement effectiveness
* Structured prompting vs free-text
* AI-driven user engagement

## ⚠️ Risks & Mitigation

| Risk              | Solution               |
| ----------------- | ---------------------- |
| LLM hallucination | Structured prompts     |
| Memory errors     | Vector DB + schema     |
| Latency           | Caching + optimization |
| Scope creep       | Strict MVP control     |

## 📦 Deliverables

* Functional MVP
* Multi-agent system
* Memory integration
* GitHub repository
* Final demo & presentation

## 🔮 Future Enhancements

* Reinforcement learning agents
* Multiplayer support
* Voice interaction
* Mobile app
* Knowledge graph integration

## 🧭 Key Engineering Principle

> Architecture defines everything.
> A well-designed system enables scalability, reliability, and performance.

## 📜 License

Academic / Educational Use

## 👨‍💻 Contributors

* Project Team (Capstone)
