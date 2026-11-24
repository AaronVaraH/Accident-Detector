# Development Log — Accident-Detector (TITAN Vision)

Chronological engineering log documenting what was built, why, commit/PR evidence, and problems encountered with their fixes.

---

## Entry 1 — 2026-10-06: Initial Architecture, Vision Pipeline & PWA Foundation
- **What we did:** Created the base repository structure including `main.py`, `server.py`, `src/stream.py`, `src/inference.py`, `src/kinematics.py`, `src/incident_rules.py`, and the initial Progressive Web App (PWA) frontend with Vercel routing (`vercel.json`).
- **Why:** Establish a real-time computer vision pipeline using YOLOv8 + ByteTrack to detect vehicles, sudden braking/collisions, and fire/smoke hazards with a web dashboard.
- **Evidence:** Commit [`ec37f5d`](https://github.com/AaronVaraH/Accident-Detector/commit/ec37f5d)
- **Problems & Fixes:** Running synchronous inference and web serving in a single script risked blocking video frames. Fixed by separating the pipeline manager (`src/pipeline_manager.py`) from the FastAPI/Uvicorn web server (`server.py`).

## Entry 2 — 2026-10-06: Dockerization & 24/7 Cloud Hosting Setup
- **What we did:** Added `Dockerfile`, `.dockerignore`, `render.yaml`, and dynamic `$PORT` binding for cloud deployment on Render, along with `DEPLOYMENT.md`.
- **Why:** Enable repeatable, containerized 24/7 cloud hosting and automated deployments from `main`.
- **Evidence:** Commits [`6929f53`](https://github.com/AaronVaraH/Accident-Detector/commit/6929f53), [`29f87a8`](https://github.com/AaronVaraH/Accident-Detector/commit/29f87a8)
- **Problems & Fixes:** Hardcoded local port `8000` failed Render health checks. Fixed by reading `PORT` from the environment and configuring Uvicorn with proxy headers.

## Entry 3 — 2026-10-06: Custom Fire Model Bundling & Live Camera Cloud Streaming
- **What we did:** Bundled custom fire/smoke weights (`models/fire_smoke.pt`, `models/lighter_flame.onnx`), added graceful fallback in `FireDetector`, enabled live local video feed + AI overlay, and added anti-buffering headers for MJPEG streaming.
- **Why:** Ensure fire detection works out-of-the-box in containers without external weight downloads and prevent proxy buffering delays on live video.
- **Evidence:** Commits [`e2892f7`](https://github.com/AaronVaraH/Accident-Detector/commit/e2892f7), [`d721590`](https://github.com/AaronVaraH/Accident-Detector/commit/d721590), [`acf981a`](https://github.com/AaronVaraH/Accident-Detector/commit/acf981a)
- **Problems & Fixes:** Cloud reverse proxies buffered MJPEG chunks, causing multi-second lag, and missing fire weights crashed startup. Fixed by adding `X-Accel-Buffering: no` / cache-control headers and a graceful fallback when custom weights are absent.

## Entry 4 — 2026-10-06: 512 MB RAM Optimization, Gzip Compression & Stream Iterator Fix
- **What we did:** Slimmed the Docker image for Render's 512 MB Free tier, added Gzip compression and DOM throttling in the PWA, and fixed the demo video path and stream iterator.
- **Why:** Prevent out-of-memory (OOM) container restarts on Render Free instances and keep the browser UI responsive under 30 FPS telemetry updates.
- **Evidence:** Commits [`752b409`](https://github.com/AaronVaraH/Accident-Detector/commit/752b409), [`4511300`](https://github.com/AaronVaraH/Accident-Detector/commit/4511300), [`b5e0134`](https://github.com/AaronVaraH/Accident-Detector/commit/b5e0134)
- **Problems & Fixes:** Container exceeded 512 MB RAM during startup and demo video failed to resolve in Linux containers. Fixed by switching to `opencv-python-headless`, limiting worker concurrency, and resolving demo paths relative to `BASE_DIR`.

## Entry 5 — 2026-10-28: License Plate Detection (ALPR) & Multilingual Support
- **What we did:** Integrated license plate detection (`src/plate_detector.py`) and updated the responsive PWA UI (`pwa/`) with Spanish/English localization (`src/i18n.py`).
- **Why:** Capture vehicle plate evidence during detected incidents and support bilingual operators.
- **Evidence:** Commits [`2fe5ef1`](https://github.com/AaronVaraH/Accident-Detector/commit/2fe5ef1), [`eff111c`](https://github.com/AaronVaraH/Accident-Detector/commit/eff111c)
- **Problems & Fixes:** Plate OCR slowed down the main inference loop when run on every frame. Fixed by running ALPR selectively when an incident or vehicle ROI is triggered.

## Entry 6 — 2026-11-03: Incident Enrichment & CAD-911 Dispatch Microservice
- **What we did:** Built the decoupled REST microservice in `services/incident_enrichment_service/` with `X-API-Key` authentication, OpenWeatherMap + Open-Meteo fallback, smoke dispersion calculation, CAD-911 ticket generation, and 10 automated `pytest` unit tests.
- **Why:** Decouple external weather/dispatch network I/O from the real-time computer vision loop so third-party latency never drops video frames.
- **Evidence:** Commit [`96fa30c`](https://github.com/AaronVaraH/Accident-Detector/commit/96fa30c)
- **Problems & Fixes:** External weather API timeouts could block incident dispatch. Fixed by adding a 3-second timeout, automatic fallback to Open-Meteo, and a local nominal-weather degradation mode.

## Entry 7 — 2026-11-03: Fire/Smoke Threshold Tuning & Client Resilience
- **What we did:** Tuned fire/smoke persistence thresholds (`src/incident_rules.py`), added `src/microservice_client.py` with safe fallbacks, and updated PWA tactical controls.
- **Why:** Reduce false-positive fire alarms from headlights/reflections and ensure the main app stays operational even when the enrichment microservice is unreachable.
- **Evidence:** Commits [`a913174`](https://github.com/AaronVaraH/Accident-Detector/commit/a913174), [`4f5b830`](https://github.com/AaronVaraH/Accident-Detector/commit/4f5b830)
- **Problems & Fixes:** Flickering smoke detections reset persistence counters too aggressively. Fixed by using soft decay (`count - 1`) in `IncidentRuleEngine.evaluate()`.

## Entry 8 — 2026-11-04 & 2026-11-05: Production Render + Vercel Storage Integration
- **What we did:** Configured `ENRICHMENT_SERVICE_URL` and `ENRICHMENT_SERVICE_API_KEY` for Render production, added `/historial` audit view, and connected Vercel Postgres + Vercel Blob (`src/database.py`).
- **Why:** Persist incident dossiers and JPEG snapshots outside ephemeral container filesystems.
- **Evidence:** Commits [`c936754`](https://github.com/AaronVaraH/Accident-Detector/commit/c936754), [`c2c5b73`](https://github.com/AaronVaraH/Accident-Detector/commit/c2c5b73)
- **Problems & Fixes:** Ephemeral container storage wiped incident history on every Render redeploy. Fixed by persisting `incidents_backlog`, `plates_backlog`, and `vehicles_registry` in managed PostgreSQL and uploading snapshots to Vercel Blob.

## Entry 9 — 2026-11-23: Sidebar SPA Layout, Brand Assets & HUD Cleanup
- **What we did:** Refactored the PWA into a sidebar SPA layout with brand assets, cleaned up HUD labels, and added favicon routes.
- **Why:** Improve operator ergonomics and navigation between live monitoring and incident history.
- **Evidence:** Commit [`85cf271`](https://github.com/AaronVaraH/Accident-Detector/commit/85cf271)
- **Problems & Fixes:** Missing favicon routes produced `404` noise in browser DevTools. Fixed by adding explicit `/favicon*` static routes in `server.py`.

## Entry 10 — 2026-11-23: Core Unit Tests, GitHub Actions CI, Deployment Playbook & Branch Protection
- **What we did:** Added `tests/test_core_unit.py` (8 unit tests for `IncidentRuleEngine`, `IncidentEvent`, and `VehicleKinematicsTracker`), created `.github/workflows/ci.yml` (`unit-tests` job running all 18 `pytest` tests on every PR), documented the 5-phase deployment process in `docs/DEPLOYMENT.md`, updated `README.md`, and enabled branch protection on `main` (requiring PRs, 1 approval, and passing `unit-tests` status check).
- **Why:** Enforce automated quality gates on every pull request and provide a repeatable deployment/rollback playbook.
- **Evidence:**
  - Initial CI & docs commit: [`f8c035e`](https://github.com/AaronVaraH/Accident-Detector/commit/f8c035e)
  - Blocked-then-fixed Pull Request: [PR #1](https://github.com/AaronVaraH/Accident-Detector/pull/1) (blocked by failing `unit-tests` run [`45298554471`](https://github.com/AaronVaraH/Accident-Detector/actions/runs/45298554471), then fixed and merged).
- **Problems & Fixes:**
  1. Root `requirements.txt` lacked `pytest` and `httpx`, which would cause `pytest` to fail on a clean clone. Fixed by adding `pytest>=8.0.0` and `httpx>=0.27.0` to `requirements.txt`.
  2. On Ubuntu CI runners, invoking bare `pytest` raised `ModuleNotFoundError: No module named 'src'` because `.` was not on `sys.path`. Fixed by adding `pytest.ini` (`pythonpath = .`) and running `python -m pytest` in `.github/workflows/ci.yml`.
  3. In [PR #1](https://github.com/AaronVaraH/Accident-Detector/pull/1), `test_rule_engine_smoke_only_detection` initially failed with an assertion mismatch (`"fuego_detectado"` vs `"humo_detectado"`), causing branch protection to block the merge (`mergeStateStatus: BLOCKED`). Fixed the assertion in `tests/test_core_unit.py` so all 18 unit tests pass in CI before merging.
