# Resume & JD Analyzer

> **AI-powered resume-to-JD matching with explainable scores, radar charts, and PDF reports.**
> Uses transformer embeddings, skill ontology graphs, section-weighted scoring, and LLM extraction with round-robin API key rotation.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: Extraction (Gemini LLM → Structured JSON)          │
│           • Batch extraction (2-6 resumes/call)              │
│           • API key round-robin on 429 errors                │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: Embedding (BGE-large-en-v1.5 → 1024-d vectors)    │
│           • Section-level embeddings (skills/exp/edu/proj)   │
│           • Asymmetric query prefixes for JDs                │
├──────────────────────────────────────────────────────────────┤
│  Layer 3: Storage (Qdrant HNSW + PostgreSQL)                 │
│           • Vector store: COSINE distance, m=16, ef=100      │
│           • Relational: structured data + match records      │
├──────────────────────────────────────────────────────────────┤
│  Layer 4: Scoring (4-tier skill matching + ontology)         │
│           • Direct → Substring → Ontology → Semantic match   │
│           • 246 skill implications in the ontology graph      │
│           • Role-level weighted scoring (intern → lead)      │
├──────────────────────────────────────────────────────────────┤
│  Layer 5: Explainability (Reports + PDF export)              │
│           • Radar charts, grade badges, red flag detection    │
│           • Professional PDF reports with ReportLab           │
└──────────────────────────────────────────────────────────────┘
```

**Tech Stack:**
- **Backend:** Python 3.11+, FastAPI, Celery, SQLAlchemy (async)
- **LLM:** Google Gemini API (extraction + explanation) with round-robin key rotation
- **Embeddings:** `BAAI/bge-large-en-v1.5` (sentence-transformers, 1024-dim)
- **Vector DB:** Qdrant (self-hosted via Docker)
- **Database:** PostgreSQL 15 (async via asyncpg)
- **Queue:** Redis 7 + Celery (solo pool on Windows)
- **Frontend:** Next.js 14 (App Router) with glassmorphism dark theme
- **PDF:** ReportLab for professional match reports

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Link |
|------|---------|------|
| Docker Desktop | Latest | [Download](https://www.docker.com/products/docker-desktop/) |
| Python | 3.11+ | [Download](https://www.python.org/downloads/) |
| Node.js | 18+ | [Download](https://nodejs.org/) |
| Gemini API Key(s) | Free tier | [Get keys](https://aistudio.google.com/apikey) |

### Step 1: Clone & Configure

```bash
git clone <your-repo-url>
cd resume_analyzer

# Create your environment file
cp .env.example .env

# Edit .env — add your Gemini API key(s):
# GOOGLE_API_KEY=your-key-here
# GOOGLE_API_KEYS=key1,key2,key3    ← optional, for round-robin rotation
```

### Step 2: Start Infrastructure (Docker)

```powershell
# Terminal 1 — from project root
docker compose up postgres redis qdrant
# Wait for: "database system is ready to accept connections"
```

### Step 3: Start the Backend

```powershell
# Terminal 2
cd backend
python -m venv venv
..\venv\Scripts\Activate.ps1    # Windows
pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Wait for: "Application startup complete"
```

### Step 4: Start the Celery Worker

```powershell
# Terminal 3
cd backend
..\venv\Scripts\Activate.ps1
celery -A workers.tasks worker --loglevel=info --pool=solo
# Wait for: "celery@hostname ready."
```

> **Note:** Use `--pool=solo` on Windows. On Linux/Mac, use `--concurrency=4`.

### Step 5: Start the Frontend

```powershell
# Terminal 4
cd frontend
npm install
npm run dev
# Open: http://localhost:3000
```

### First Run Workflow

1. Click **🗑 Flush All Data** on the Dashboard (clears any stale data)
2. Go to **Resumes** → drag-drop PDF/DOCX files
3. Go to **Jobs** → upload a JD file
4. Go to **Match** → select JD → click **🚀 Run Match**
5. Watch the 5-step progress bar → view results with radar charts
6. Click **📄 Download PDF Report** for the professional report

---

## 📁 Project Structure

```
resume_analyzer/
├── backend/
│   ├── api/
│   │   └── routes/
│   │       ├── resume.py          # Resume upload/list/delete
│   │       ├── jd.py              # JD upload/list/delete
│   │       ├── match.py           # Match trigger/results + PDF export
│   │       └── admin.py           # Flush all data endpoint
│   ├── core/
│   │   ├── extractor.py           # Layer 1: Gemini extraction + batch + key rotation
│   │   ├── embedder.py            # Layer 2: BGE embeddings (section-level)
│   │   ├── vector_store.py        # Layer 3: Qdrant operations
│   │   ├── scorer.py              # Layer 4: 4-tier scoring + debug logs
│   │   ├── ontology.py            # Layer 4b: 246-edge skill implication graph
│   │   ├── explainer.py           # Layer 5: Human-readable explanations
│   │   └── pdf_export.py          # PDF report generation (ReportLab)
│   ├── workers/
│   │   ├── tasks.py               # Celery task definitions
│   │   └── pipeline.py            # Pipeline orchestration
│   ├── scripts/
│   │   └── validate_e2e.py        # End-to-end validation script
│   ├── models/                    # Pydantic schemas
│   ├── db/                        # PostgreSQL setup (async SQLAlchemy)
│   ├── config.py                  # Environment config (pydantic-settings)
│   └── main.py                    # FastAPI entry point
├── frontend/                      # Next.js 14 dashboard
│   └── src/app/
│       ├── page.js                # Dashboard + flush button
│       ├── resumes/               # Resume upload page
│       ├── jobs/                   # JD upload page
│       └── match/page.js          # Match page (radar chart, progress bar)
├── docker-compose.yml             # Infrastructure services
├── .env.example                   # Environment template
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
| `GET` | `/api/match/export/{job_id}/pdf` | **Download PDF report** |
| `DELETE` | `/api/admin/flush` | **Wipe all data** (PG + Qdrant + Redis + uploads) |

---

## 📊 How Scoring Works

### Role-Level Weights

| Level | Skills | Experience | Education | Projects |
|-------|--------|------------|-----------|----------|
| Intern | 25% | 15% | 35% | 25% |
| Junior | 35% | 25% | 20% | 20% |
| Mid | 40% | 35% | 15% | 10% |
| Senior | 35% | 45% | 10% | 10% |
| Lead | 30% | 50% | 10% | 10% |

### 4-Tier Skill Matching

1. **Tier 1 — Direct Match:** Case-insensitive exact match (1.0 weight)
2. **Tier 2 — Substring Match:** "Machine Learning" contains "ML" (0.85 weight)
3. **Tier 3 — Ontology Match:** PyTorch → implies Python (via 246-edge graph) (0.75 weight)
4. **Tier 4 — Semantic Match:** BGE cosine similarity > 82% threshold (0.65 weight)

### Grade Assignment

| Score | Grade | Label |
|-------|-------|-------|
| ≥ 85 | A | Excellent Match |
| ≥ 70 | B | Strong Match |
| ≥ 55 | C | Moderate Match |
| ≥ 40 | D | Weak Match |
| < 40 | F | Poor Match |

---

## 🔑 API Key Round-Robin

To avoid hitting Gemini rate limits (429 errors), set multiple API keys:

```env
# .env
GOOGLE_API_KEYS=AIzaSy...key1,AIzaSy...key2,AIzaSy...key3
```

The `APIKeyRotator` automatically:
1. Starts with key #1
2. On a 429/quota error, rotates to key #2
3. Continues cycling through all keys
4. Only fails if ALL keys are exhausted

---

## 🧪 Testing

```bash
cd backend

# End-to-end validation (no infrastructure needed)
python scripts/validate_e2e.py

# Unit tests
pytest tests/ -v --cov=core
```

---

## 📝 License

MIT
