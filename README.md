# Puchoo.ai

Puchoo.ai is a production-grade secure multilingual Text-to-SQL analytics platform. It turns natural-language analytics questions into transparent SQL proposals using a deliberate **ask → review → run → verify** workflow over your existing databases.

It implements a **FastAPI backend as the sole security boundary** and a **React SPA (Vite)** for a premium, secure presentation layer.

## Architecture

- **Backend (`apps/core/` & `apps/api/`)**: FastAPI exposes the core Python execution, verification, and guardrail logic. It handles all authentication, session state, and security. No credentials are leaked to the client.
- **Frontend (`frontend/`)**: Vite + React SPA handling presentation only. Rich Vanilla CSS design system.

## Run locally

Use Python 3.10 or newer.

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the FastAPI backend:**
   ```bash
   uvicorn apps.api.main:app --reload --port 8000
   ```

3. **Start the React frontend:**
   In a new terminal window:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. Open [http://localhost:5173](http://localhost:5173) in your browser.

## Safe execution and verification

- A question is answered automatically only after its SQL passes the read-only guardrails and database query-plan validation.
- The execution boundary parses SQL with SQLGlot, accepts one `SELECT` only, rejects data-changing CTEs and multiple statements, and clamps the outermost `LIMIT`.
- No credentials or source data are stored in the React UI. The FastAPI layer maintains strict session and tenant boundaries.

## Configuration

Copy `.env.example` to a local, uncommitted `.env` when credentials are ready. The default SQL provider is the local MLX server, so it needs no model API key for basic SQL generation. `ANTHROPIC_API_KEY` enables the independent post-execution verifier.
