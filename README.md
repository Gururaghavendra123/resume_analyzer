# Resume & JD Analyzer

> **Semantically match resumes to job descriptions with explainable scores.**  
> ML-powered matching engine using transformer embeddings, skill ontology graphs, and section-weighted scoring.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Extraction (Gemini LLM → Structured JSON)     │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Embedding (BGE-large-en-v1.5 → 1024-d vecs)  │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Storage (Qdrant vector DB + PostgreSQL)       │
├─────────────────────────────────────────────────────────┤
│  Layer 4: Scoring (Weighted section scoring + Ontology) │
├─────────────────────────────────────────────────────────┤
│  Layer 5: Explainability (Human-readable match reports) │
└─────────────────────────────────────────────────────────┘
```

**Tech Stack:**
- **Backend:** Python 3.11+, FastAPI, Celery, SQLAlchemy
- **LLM:** Google Gemini API (extraction + explanation)
- **Embeddings:** `BAAI/bge-large-en-v1.5` (sentence-transformers)
- **Vector DB:** Qdrant (self-hosted via Docker)
- **Database:** PostgreSQL 15
- **Queue:** Redis 7 + Celery
- **Frontend:** Next.js 14 (App Router)

---

## 🚀 Quick Start

### Prerequisites

1. **Docker Desktop** — [Download](https://www.docker.com/products/docker-desktop/)
   - Install with WSL 2 backend (Windows)
   - Verify: `docker --version`

2. **Python 3.11+** — [Download](https://www.python.org/downloads/)
   - Verify: `python --version`

3. **Node.js 18+** — [Download](https://nodejs.org/)
   - Verify: `node --version`

4. **Google Gemini API Key** — [Get one free](https://aistudio.google.com/apikey)

### Step 1: Clone & Configure

```bash
git clone <your-repo-url>
cd resume-jd-analyzer

# Create your environment file
cp .env.example .env

# Edit .env and add your Gemini API key:
# GOOGLE_API_KEY=your-actual-key-here
```

### Step 2: Start Infrastructure (Docker)

```bash
# Start Qdrant, PostgreSQL, and Redis
docker-compose up qdrant postgres redis -d

# Wait ~10 seconds for services to be ready
# Verify:
docker ps   # Should show 3 running containers
```

### Step 3: Start the Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn main:app --reload --port 8000
```

The API will be available at http://localhost:8000  
Interactive docs: http://localhost:8000/docs

### Step 4: Start the Celery Worker

Open a **second terminal**:

```bash
cd backend
venv\Scripts\activate

# Start Celery worker
celery -A workers.tasks worker --loglevel=info --pool=solo
```

> **Note:** Use `--pool=solo` on Windows. On Linux/Mac, use `--concurrency=4`.

### Step 5: Start the Frontend

Open a **third terminal**:

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000

---

## 📁 Project Structure

```
resume-jd-analyzer/
├── backend/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── resume.py      # Resume upload/list/delete
│   │   │   ├── jd.py          # JD upload/list/delete
│   │   │   └── match.py       # Match trigger/results
│   │   └── middleware.py       # Logging + error handling
│   ├── core/
│   │   ├── extractor.py       # Layer 1: Gemini extraction
│   │   ├── embedder.py        # Layer 2: BGE embeddings
│   │   ├── vector_store.py    # Layer 3: Qdrant ops
│   │   ├── scorer.py          # Layer 4: Section scoring
│   │   ├── ontology.py        # Layer 4b: Skill graph
│   │   └── explainer.py       # Layer 5: Explanations
│   ├── workers/
│   │   ├── tasks.py           # Celery task definitions
│   │   └── pipeline.py        # Pipeline orchestration
│   ├── models/                # Pydantic schemas
│   ├── db/                    # PostgreSQL setup
│   ├── config.py              # Environment config
│   └── main.py                # FastAPI entry point
├── frontend/                  # Next.js dashboard
├── docker-compose.yml         # Infrastructure services
├── .env.example               # Environment template
└── README.md
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/resume/upload` | Upload single resume (PDF/DOCX/TXT) |
| `POST` | `/api/resume/bulk-upload` | Upload multiple resumes |
| `GET` | `/api/resume/{id}` | Get resume structured data |
| `GET` | `/api/resume/` | List all resumes |
| `DELETE` | `/api/resume/{id}` | Delete resume + vectors |
| `POST` | `/api/jd/upload` | Upload job description |
| `GET` | `/api/jd/{id}` | Get JD structured data |
| `GET` | `/api/jd/` | List all JDs |
| `DELETE` | `/api/jd/{id}` | Delete JD + vectors |
| `POST` | `/api/match/run` | Trigger match (JD vs all resumes) |
| `GET` | `/api/match/results/{job_id}` | Poll match results |
| `GET` | `/api/match/detail/{resume_id}/{jd_id}` | Specific match result |
| `GET` | `/api/match/export/{job_id}` | Export results as JSON |

---

## 🧪 Testing

```bash
cd backend
pytest tests/ -v --cov=core
```

---

## 📊 How Scoring Works

Scores are **weighted by role level**:

| Level | Skills | Experience | Education | Projects |
|-------|--------|------------|-----------|----------|
| Intern | 25% | 15% | 35% | 25% |
| Junior | 35% | 25% | 20% | 20% |
| Mid | 40% | 35% | 15% | 10% |
| Senior | 35% | 45% | 10% | 10% |
| Lead | 30% | 50% | 10% | 10% |

**Skill matching** uses three tiers:
1. **Direct match** — exact case-insensitive match
2. **Ontology match** — e.g., PyTorch implies Python (via skill graph)
3. **Semantic match** — embedding cosine similarity > 82%

---

## 📝 License

MIT
