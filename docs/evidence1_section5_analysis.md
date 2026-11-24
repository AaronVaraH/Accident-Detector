# 5. Microservices and Our Web App

## 5.1 Summary of Activity 1 and Architectural Findings

From our initial architectural analysis of **Accident-Detector (TITAN Vision)**—a real-time computer vision and kinematic traffic incident detection system—running the entire application as a single monolith introduced three critical operational bottlenecks:

1. **Coupling of CPU/GPU-Intensive Workloads and Network I/O:** The computer vision pipeline (YOLOv8 + ByteTrack) processes video frames continuously in real time. Executing synchronous third-party API calls (weather, reverse geocoding, or SMS alerts) inside the same process causes external network latency to block the capture loop and drop critical video frames.
2. **Costly Asymmetric Scaling:** Monitoring multiple traffic cameras requires scaling inference nodes, whereas incident enrichment and emergency dispatch logic consume minimal compute. In a monolithic design, the entire system would have to be replicated together.
3. **Single Point of Failure:** A transient outage in an external notification or weather provider should never interrupt live video surveillance or local tactical alerts.

To solve these issues, the web application was decoupled into a **microservices-oriented architecture** (documented in `docs/product_analysis.md` and `DEPLOYMENT.md`):

- **Core Web App & AI Engine (`server.py`):** A FastAPI + Uvicorn server that serves the Progressive Web App (PWA) dashboard (`/` and `/historial`), MJPEG video streaming (`/api/stream`), real-time telemetry and smartphone camera uplink WebSockets (`/ws/telemetry`, `/ws/uplink`), and the YOLOv8n inference pipeline.
- **Incident Enrichment & Dispatch Microservice (`services/incident_enrichment_service/main.py`):** An independent, lightweight REST microservice that ingests detected incident telemetry (`POST /api/v1/incidents/evaluate-and-dispatch`), queries external weather APIs (OpenWeatherMap with Open-Meteo fallback), calculates smoke dispersion and road-grip hazards, and generates standardized `CAD-911` emergency dossiers. Both services communicate over HTTPS using `X-API-Key` authentication.

This separation aligns directly with modern cloud-native patterns (PaaS/containers and DBaaS), allowing each service to be deployed, scaled, and maintained independently.

---

## 5.2 Core Infrastructure Required for Our Web App

Deploying **Accident-Detector** in production requires five foundational cloud infrastructure components working together:

### 1. Application Server
The application server executes backend business logic, handles HTTP/WebSocket requests, and serves the frontend interface.
- **In our web app:** We run two containerized **FastAPI** application servers powered by **Uvicorn** (ASGI) and packaged with **Docker** (`Dockerfile` and `services/incident_enrichment_service/Dockerfile`), deployed on **Render** (`render.yaml`).
  - The main application server listens on port `8000` (overridden by `$PORT` in production) and runs the PWA and AI pipeline.
  - The enrichment microservice runs in its own lightweight container on port `8001` (or `$PORT` in its dedicated Render service).

### 2. Database Server
The database server provides durable, structured, and queryable persistence outside the ephemeral filesystem of application containers.
- **In our web app:** We use a managed cloud **PostgreSQL** database (**Vercel Postgres** / **Supabase PostgreSQL**) accessed through **SQLAlchemy ORM** (`DATABASE_URL` and `POSTGRES_URL_NON_POOLING` environment variables). It stores the `incidents_backlog`, `plates_backlog`, and `vehicles_registry` tables.
- To avoid bloating the relational database with binary files, JPEG evidence frames of collisions and license plates are offloaded to managed object storage (**Vercel Blob** / **Supabase Storage**, bucket `incident-evidence`).

### 3. Load Balancer
A load balancer (and reverse proxy) distributes incoming client traffic across healthy application instances, performs automated health checks, and handles TLS termination.
- **In our web app:** In production on **Render**, the platform's managed reverse proxy / load balancer receives external HTTPS requests, monitors service availability via `/api/health` (main server) and `/health` (microservice), and forwards traffic to the Docker containers. Uvicorn is explicitly configured with `proxy_headers=True` and `forwarded_allow_ips="*"` in `server.py` to trust forwarded client headers from the cloud proxy. Additionally, `vercel.json` defines URL rewrite rules for routing PWA static assets cleanly.

### 4. Domain
A domain name maps human-readable hostnames to cloud network endpoints via DNS records (e.g., `CNAME` or `A` records), decoupling clients and microservices from ephemeral IP addresses.
- **In our web app:** Each deployed service exposes a stable managed HTTPS subdomain—such as `accident-detector.onrender.com` for the main PWA and `titan-enrichment-microservice.onrender.com` for the REST microservice (configured via `ENRICHMENT_SERVICE_URL` in `render.yaml`). This enables reliable service-to-service communication and seamless browser access across desktop and mobile devices.

### 5. Security Certificate (SSL/TLS)
An SSL/TLS certificate encrypts data in transit (HTTPS for REST/PWA and WSS for WebSockets) and verifies server identity to prevent man-in-the-middle attacks.
- **In our web app:** TLS is not only a security best practice—it is a strict functional requirement. Modern browsers block **Service Workers** (`sw.js`) and **smartphone camera access** (`/ws/uplink`) on insecure HTTP origins. In production, Render automatically provisions and renews TLS certificates while the container enforces `FORCE_HTTPS=true`. For local LAN testing with mobile devices, `server.py` also supports native HTTPS (`python server.py --ssl`) using locally generated SSL certificates.

---

## 5.3 End-to-End Request Flow Summary

| Layer | Component | Role in *Accident-Detector* |
| :--- | :--- | :--- |
| **1. Naming** | **Domain (DNS)** | Resolves `accident-detector.onrender.com` to the cloud edge. |
| **2. Encryption** | **SSL/TLS Certificate** | Secures HTTPS/WSS traffic so the PWA can install Service Workers and stream mobile camera video. |
| **3. Routing** | **Load Balancer / Proxy** | Terminates TLS, checks `/api/health`, and forwards traffic to the container. |
| **4. Compute** | **Application Servers** | `server.py` (FastAPI/Uvicorn) processes video and calls the `incident_enrichment_service` microservice via `X-API-Key`. |
| **5. Persistence** | **Database & Object Storage** | PostgreSQL (`incidents_backlog`, `plates_backlog`, `vehicles_registry`) + Blob Storage persist incident records and JPEG evidence. |

