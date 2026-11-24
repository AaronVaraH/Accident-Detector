# Deployment Process — Accident-Detector (TITAN Vision)

This document defines the repeatable, 5-phase deployment workflow for **Accident-Detector** (`server.py` main web app + PWA) and the **Incident Enrichment Microservice** (`services/incident_enrichment_service/main.py`) hosted on **Render** with **Vercel Postgres & Blob** storage.

For initial service provisioning and environment variable tables, see the root [DEPLOYMENT.md](../DEPLOYMENT.md).

---

## 1. Before (Pre-Deployment Checklist)

Complete every check before merging to `main` or triggering a production deploy:

1. **Clean Working Tree & Branch:**
   - Ensure all changes are on a feature/fix branch and a Pull Request targeting `main` is open.
   - Never commit `.env`, API keys, tokens, or certificates (`git status` and `.gitignore` verified).
2. **Automated Tests Green:**
   - Run the unit test suite locally:
     ```bash
     pytest tests/test_core_unit.py services/incident_enrichment_service/tests/test_microservice.py -v
     ```
   - Confirm the GitHub Actions CI check (`unit-tests`) is green on the PR.
3. **Pull Request Review & Merge Rules:**
   - Obtain at least **1 approval** on the PR.
   - Verify no merge conflicts exist with `main`.
4. **Environment & Secrets Audit (Render Dashboard):**
   - **Main App (`accident-detector`):** Verify `ENVIRONMENT=production`, `FORCE_HTTPS=true`, `DATABASE_URL`, `BLOB_READ_WRITE_TOKEN`, `ENRICHMENT_SERVICE_URL`, `ENRICHMENT_SERVICE_API_KEY`, and third-party keys (`OPENWEATHER_API_KEY`, `ROBOFLOW_API_KEY`, `TWILIO_*`) are set in Render's Environment tab.
   - **Microservice (`titan-enrichment-microservice`):** Verify `ENVIRONMENT=production`, `SERVICE_API_KEY` (must match `ENRICHMENT_SERVICE_API_KEY`), and `OPENWEATHER_API_KEY`.
5. **Docker Build Sanity Check (Optional Local):**
   - If `Dockerfile` or `requirements.txt` changed, confirm the container builds cleanly:
     ```bash
     docker build -t accident-detector:precheck .
     ```

---

## 2. Deploy

1. **Merge the Pull Request into `main`:**
   - Once `unit-tests` passes and the PR is approved, click **Squash and merge** (or **Merge pull request**) on GitHub.
2. **Automatic Render Deployment:**
   - Render watches the `main` branch via `render.yaml` and automatically triggers a Docker build and rollout for:
     - **Main Web Service** (`Dockerfile` at repo root)
     - **Enrichment Microservice** (`services/incident_enrichment_service/Dockerfile`)
3. **Manual Deploy (if auto-deploy is paused):**
   - Open the **Render Dashboard** -> select the service -> **Manual Deploy** -> **Deploy latest commit**.
4. **Monitor Build Logs:**
   - Watch the Render **Logs** tab until you see:
     - `Uvicorn running on http://0.0.0.0:$PORT`
     - `Your service is live`

---

## 3. Verify (Post-Deployment Smoke Tests)

Run these checks immediately after Render marks the deploy as **Live**:

1. **Health Endpoints (CLI / Browser):**
   ```bash
   curl -fsS https://accident-detector.onrender.com/api/health
   curl -fsS https://titan-enrichment-microservice.onrender.com/health
   ```
   - Expected: HTTP `200 OK` with `"status": "healthy"` (microservice) and valid JSON status (main server).
2. **UI & PWA Verification:**
   - Open `https://accident-detector.onrender.com/` in a private browser window.
   - Confirm the HUD loads, video stream / demo feed renders, and no `500` or CORS errors appear in DevTools Console.
   - Open `https://accident-detector.onrender.com/historial` and confirm the incident backlog loads from PostgreSQL.
3. **End-to-End Microservice Integration:**
   - Trigger **EVALUAR & DESPACHAR CAD-911** from the situational panel (or test `GET /api/v1/environmental-hazards?lat=19.3012&lon=-99.1824`) and confirm a `CAD-911-MEX-...` ticket or weather hazard payload is returned.

---

## 4. Roll Back

If verification fails, error rates spike, or a regression is observed in production:

1. **Immediate Platform Rollback (Fastest — < 2 minutes):**
   - Open **Render Dashboard** -> select the affected service (`accident-detector` or `titan-enrichment-microservice`) -> **Events / Deploys** tab.
   - Locate the last known-good deploy -> click **Rollback to this deploy**.
   - Re-run the **Verify** health checks once the rollback is live.
2. **Git Revert (Permanent Code Fix):**
   - Create a revert branch from `main`:
     ```bash
     git checkout main && git pull origin main
     git checkout -b revert/bad-deploy
     git revert <bad-commit-sha>
     git push -u origin revert/bad-deploy
     ```
   - Open a Pull Request, wait for `unit-tests` CI to pass, get approval, and merge to `main`.
3. **Database Safety:**
   - SQLAlchemy uses `Base.metadata.create_all()` (additive schema). Avoid destructive `DROP`/`ALTER` migrations in hotfixes; if a schema change caused the issue, restore from Vercel Postgres / Supabase point-in-time backup before re-enabling traffic.

---

## 5. Record

Log every production deployment and rollback in `docs/DEVELOPMENT_LOG.md` with:
- **Date & Time (UTC / Local)**
- **Commit SHA / PR Link**
- **Deployed Services** (`main server`, `enrichment microservice`, or both)
- **Verification Result** (health check status, smoke test outcome)
- **Issues / Rollback Notes** (if any occurred, root cause and fix)
