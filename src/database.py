"""
Módulo de Persistencia con ORM (SQLAlchemy 2.0) + Vercel Blob Storage.
Se conecta directamente a la base de datos PostgreSQL creada desde Vercel (`POSTGRES_URL_NON_POOLING` / `DATABASE_URL`)
y ejecuta `Base.metadata.create_all(engine)` automáticamente al iniciar, sin requerir acceso manual al panel de Supabase.
"""

import csv
import io
import logging
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, desc
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import JSON

from config import settings

logger = logging.getLogger("BacklogORM")

Base = declarative_base()

# Tipo JSON compatible tanto con PostgreSQL (JSONB) como con SQLite en pruebas locales
JsonColumnType = JSON().with_variant(JSONB(), "postgresql")


class IncidentBacklogModel(Base):
    """Modelo ORM para la tabla `incidents_backlog`."""

    __tablename__ = "incidents_backlog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    incident_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(32), nullable=False, default="ALTO")
    status = Column(String(32), nullable=False, default="PENDIENTE", index=True)
    title = Column(String(255), nullable=False)
    subtitle = Column(Text, default="")
    camera_id = Column(String(64), nullable=False, default="camera_01")
    source = Column(String(128), default="client_cam")
    frame_idx = Column(Integer, default=0)
    plate = Column(String(32), nullable=True, index=True)
    vehicle_data = Column(JsonColumnType, default=dict)
    telemetry = Column(JsonColumnType, default=dict)
    enrichment = Column(JsonColumnType, default=dict)
    snapshot_url = Column(Text, nullable=True)
    dispatch_ticket_id = Column(String(64), nullable=True)
    dispatch_status = Column(String(32), default="PENDING")
    notes = Column(Text, default="")

    def to_dict(self) -> Dict[str, Any]:
        created_iso = self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat()
        ts_short = created_iso[11:19] if len(created_iso) >= 19 else created_iso
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "created_at": created_iso,
            "timestamp": ts_short,
            "incident_type": self.incident_type,
            "type": self.incident_type,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "subtitle": self.subtitle or "",
            "camera_id": self.camera_id,
            "source": self.source,
            "frame_idx": self.frame_idx or 0,
            "plate": self.plate,
            "vehicle_data": self.vehicle_data or {},
            "vehicle": self.vehicle_data or {},
            "telemetry": self.telemetry or {},
            "enrichment": self.enrichment or {},
            "snapshot_url": self.snapshot_url,
            "dispatch_ticket_id": self.dispatch_ticket_id,
            "dispatch_status": self.dispatch_status,
            "notes": self.notes or "",
        }


class PlateBacklogModel(Base):
    """Modelo ORM para la tabla `plates_backlog`."""

    __tablename__ = "plates_backlog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    plate = Column(String(32), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    vehicle_id = Column(Integer, nullable=True)
    camera_id = Column(String(64), nullable=False, default="camera_01")
    vehicle_data = Column(JsonColumnType, default=dict)
    thumbnail_url = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else datetime.now(timezone.utc).isoformat(),
            "plate": self.plate,
            "confidence": round(float(self.confidence or 0.0), 2),
            "vehicle_id": self.vehicle_id,
            "camera_id": self.camera_id,
            "vehicle_data": self.vehicle_data or {},
            "thumbnail_url": self.thumbnail_url,
        }


class VehicleRegistryModel(Base):
    """Modelo ORM para el padrón vehicular `vehicles_registry`."""

    __tablename__ = "vehicles_registry"

    plate = Column(String(32), primary_key=True)
    brand = Column(String(64), nullable=False)
    model = Column(String(64), nullable=False)
    year = Column(Integer, nullable=False, default=2020)
    color = Column(String(64), default="Blanco")
    vehicle_type = Column(String(64), default="Sedán")
    fuel_type = Column(String(64), default="Gasolina")
    vin = Column(String(64), nullable=True)
    jurisdiction = Column(String(128), default="Ciudad de México")
    owner_type = Column(String(64), default="Particular")
    stolen_status = Column(String(128), default="SIN REPORTE DE ROBO")
    is_stolen = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def normalize_sqlalchemy_url(raw_url: str) -> str:
    """
    Limpia la cadena de conexión de Vercel Postgres / Supabase (`postgres://...`)
    para que sea 100% compatible con SQLAlchemy + psycopg2 (`postgresql+psycopg2://...`),
    removiendo parámetros propietarios de Prisma/PgBouncer (`supa`, `pgbouncer`).
    """
    if not raw_url:
        return ""
    url = raw_url.strip().strip("\"'")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]

    parsed = urlparse(url)
    allowed_params = {"sslmode", "connect_timeout", "application_name"}
    clean_query = [(k, v) for k, v in parse_qsl(parsed.query) if k in allowed_params]
    return urlunparse(parsed._replace(query=urlencode(clean_query)))


class BacklogORMManager:
    """
    Gestor de Backlog impulsado por SQLAlchemy ORM y Vercel Blob Storage.
    Auto-crea las tablas en PostgreSQL al arrancar (`Base.metadata.create_all`)
    y procesa las inserciones en un hilo en segundo plano para no afectar los FPS del video.
    """

    def __init__(self, database_url: Optional[str] = None):
        raw_db_url = database_url or settings.DATABASE_URL or ""
        self.database_url = normalize_sqlalchemy_url(raw_db_url)
        self.vercel_blob_token = settings.BLOB_READ_WRITE_TOKEN or ""
        self.supabase_url = (settings.SUPABASE_URL or "").rstrip("/")
        self.supabase_key = settings.SUPABASE_KEY or ""
        self.bucket_name = settings.SUPABASE_BUCKET or "incident-evidence"

        self._session_http = requests.Session()
        self._lock = threading.Lock()
        self._init_lock = threading.Lock()

        self.engine = None
        self.SessionLocal = None
        self._incidents_cache: List[Dict[str, Any]] = []
        self._plates_cache: List[Dict[str, Any]] = []
        self._last_sync_ts: float = 0.0
        self._cloud_reachable: bool = False
        self._tables_created: bool = False
        self._last_error: Optional[str] = None

        self._write_queue: queue.Queue = queue.Queue(maxsize=250)
        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._background_orm_worker, daemon=True)
        self._worker_thread.start()

        if self.is_configured:
            threading.Thread(target=self.init_orm_and_sync, daemon=True).start()

    @property
    def is_configured(self) -> bool:
        return bool(self.database_url and "tu-proyecto" not in self.database_url)

    def init_orm_and_sync(self) -> bool:
        """
        Inicializa el motor SQLAlchemy, ejecuta `Base.metadata.create_all(engine)` para
        crear automáticamente las tablas en el PostgreSQL de Vercel/Supabase, y carga el backlog.
        """
        if not self.is_configured:
            return False

        with self._init_lock:
            try:
                if self.engine is None:
                    self.engine = create_engine(
                        self.database_url,
                        pool_pre_ping=True,
                        pool_size=3,
                        max_overflow=5,
                        connect_args={"connect_timeout": 8},
                    )
                    self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

                # Migración automática de esquema (equivalente a `prisma db push`)
                if not self._tables_created:
                    Base.metadata.create_all(bind=self.engine, checkfirst=True)
                    self._tables_created = True
                    logger.info("Tablas PostgreSQL verificadas/creadas automáticamente mediante SQLAlchemy ORM.")

                self._cloud_reachable = True
                self._last_error = None
                return self.sync_from_cloud()
            except Exception as e:
                self._cloud_reachable = False
                self._last_error = str(e)
                logger.warning(f"No se pudo inicializar ORM contra PostgreSQL remoto: {e}")
                return False

    def configure(
        self,
        supabase_url: str = "",
        supabase_key: str = "",
        bucket_name: Optional[str] = None,
        database_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if database_url:
            self.database_url = normalize_sqlalchemy_url(database_url)
            self.engine = None
        if supabase_url:
            self.supabase_url = supabase_url.strip().rstrip("/")
        if supabase_key:
            self.supabase_key = supabase_key.strip()
        if bucket_name:
            self.bucket_name = bucket_name.strip()
        self.init_orm_and_sync()
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            inc_count = len(self._incidents_cache)
            plates_count = len(self._plates_cache)

        return {
            "provider": "SQLAlchemy ORM (PostgreSQL Vercel/Supabase) + Vercel Blob",
            "orm": "SQLAlchemy 2.x",
            "configured": self.is_configured,
            "connected": self._cloud_reachable,
            "tables_auto_created": self._tables_created,
            "mode": "postgres_orm_cloud" if self._cloud_reachable else (
                "postgres_orm_connecting" if self.is_configured else "local_memory_mirror"
            ),
            "bucket": "vercel-blob" if self.vercel_blob_token else self.bucket_name,
            "vercel_blob_configured": bool(self.vercel_blob_token),
            "backlog_counts": {
                "incidents": inc_count,
                "plates": plates_count,
                "pending_queue": self._write_queue.qsize(),
            },
            "last_sync": datetime.fromtimestamp(self._last_sync_ts, tz=timezone.utc).isoformat()
            if self._last_sync_ts > 0
            else None,
            "last_error": self._last_error,
        }

    def upload_evidence_image(self, folder: str, filename: str, image_bytes: bytes) -> Optional[str]:
        """
        Sube la imagen JPEG de evidencia a Vercel Blob (`BLOB_READ_WRITE_TOKEN`)
        y retorna la URL pública para almacenarla en PostgreSQL mediante el ORM.
        """
        if not image_bytes:
            return None

        object_path = f"{folder}/{filename}"

        # 1. Subida directa a Vercel Blob
        if self.vercel_blob_token:
            try:
                blob_url = f"https://blob.vercel-storage.com/{object_path}"
                blob_headers = {
                    "Authorization": f"Bearer {self.vercel_blob_token}",
                    "x-api-version": "7",
                    "x-content-type": "image/jpeg",
                    "x-add-random-suffix": "0",
                }
                b_resp = self._session_http.put(blob_url, data=image_bytes, headers=blob_headers, timeout=8)
                if b_resp.status_code in (200, 201):
                    data = b_resp.json()
                    if data.get("url"):
                        return str(data["url"])
            except Exception as e:
                logger.debug(f"Error subiendo imagen a Vercel Blob: {e}")

        # 2. Fallback a Supabase Storage si está disponible
        if self.supabase_url and self.supabase_key:
            try:
                upload_url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{object_path}"
                headers = {
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": "image/jpeg",
                    "x-upsert": "true",
                }
                resp = self._session_http.post(upload_url, data=image_bytes, headers=headers, timeout=8)
                if resp.status_code in (200, 201):
                    return f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{object_path}"
            except Exception:
                pass
        return None

    def record_incident(
        self,
        incident_data: Dict[str, Any],
        frame_jpeg: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        incident_id = incident_data.get("incident_id") or (
            f"INC-{now_utc.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        )
        inc_type = str(incident_data.get("type") or incident_data.get("incident_type") or "anomalia_vial")
        severity = incident_data.get("severity") or (
            "CRITICO" if "fuego" in inc_type or "colision" in inc_type else "ALTO"
        )

        record = {
            "incident_id": incident_id,
            "created_at": incident_data.get("created_at") or now_utc.isoformat(),
            "timestamp": incident_data.get("timestamp") or datetime.now().strftime("%H:%M:%S"),
            "incident_type": inc_type,
            "type": inc_type,
            "severity": severity,
            "status": incident_data.get("status", "PENDIENTE"),
            "title": incident_data.get("title", "SINIESTRO DETECTADO"),
            "subtitle": incident_data.get("subtitle", ""),
            "camera_id": incident_data.get("camera_id", "camera_01"),
            "source": str(incident_data.get("source", "client_cam")),
            "frame_idx": int(incident_data.get("frame_idx", 0)),
            "plate": incident_data.get("plate"),
            "vehicle_data": incident_data.get("vehicle") or incident_data.get("vehicle_data") or {},
            "vehicle": incident_data.get("vehicle") or incident_data.get("vehicle_data") or {},
            "telemetry": incident_data.get("telemetry") or {},
            "enrichment": incident_data.get("enrichment") or {},
            "snapshot_url": incident_data.get("snapshot_url"),
            "dispatch_ticket_id": incident_data.get("dispatch_ticket_id"),
            "dispatch_status": incident_data.get("dispatch_status", "PENDING"),
            "notes": incident_data.get("notes", ""),
        }

        with self._lock:
            self._incidents_cache.insert(0, record)
            if len(self._incidents_cache) > 500:
                self._incidents_cache.pop()

        try:
            self._write_queue.put_nowait(("incident", record, frame_jpeg))
        except queue.Full:
            pass

        return record

    def record_plate(
        self,
        plate_data: Dict[str, Any],
        crop_jpeg: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        record = {
            "created_at": plate_data.get("timestamp") or now_utc.isoformat(),
            "plate": str(plate_data.get("plate", "")),
            "confidence": float(plate_data.get("confidence", 0.0)),
            "vehicle_id": plate_data.get("vehicle_id"),
            "camera_id": plate_data.get("camera_id", "camera_01"),
            "vehicle_data": plate_data.get("vehicle_data") or {},
            "thumbnail_url": plate_data.get("thumbnail_url"),
        }

        with self._lock:
            if not self._plates_cache or self._plates_cache[0].get("plate") != record["plate"]:
                self._plates_cache.insert(0, record)
                if len(self._plates_cache) > 500:
                    self._plates_cache.pop()

        try:
            self._write_queue.put_nowait(("plate", record, crop_jpeg))
        except queue.Full:
            pass

        return record

    def upsert_vehicle(self, plate: str, vehicle_data: Dict[str, Any]) -> None:
        try:
            self._write_queue.put_nowait(("vehicle", {"plate": plate, **vehicle_data}, None))
        except queue.Full:
            pass

    def _background_orm_worker(self) -> None:
        """Hilo dedicado que persiste los modelos mediante sesiones SQLAlchemy ORM y sube blobs."""
        while self._worker_running:
            try:
                task_type, payload, image_bytes = self._write_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if not self.is_configured:
                self._write_queue.task_done()
                continue

            if not self._tables_created or self.SessionLocal is None:
                self.init_orm_and_sync()

            if self.SessionLocal is None:
                self._write_queue.task_done()
                continue

            try:
                if task_type == "incident":
                    snapshot_url = payload.get("snapshot_url")
                    if image_bytes and not snapshot_url:
                        fname = f"{payload['incident_id']}.jpg"
                        snapshot_url = self.upload_evidence_image("incidents", fname, image_bytes)
                        if snapshot_url:
                            payload["snapshot_url"] = snapshot_url

                    with self.SessionLocal() as session:
                        existing = (
                            session.query(IncidentBacklogModel)
                            .filter(IncidentBacklogModel.incident_id == payload["incident_id"])
                            .first()
                        )
                        if existing:
                            existing.status = payload["status"]
                            existing.snapshot_url = snapshot_url or existing.snapshot_url
                            existing.notes = payload.get("notes", existing.notes)
                        else:
                            row = IncidentBacklogModel(
                                incident_id=payload["incident_id"],
                                incident_type=payload["incident_type"],
                                severity=payload["severity"],
                                status=payload["status"],
                                title=payload["title"],
                                subtitle=payload.get("subtitle", ""),
                                camera_id=payload.get("camera_id", "camera_01"),
                                source=payload.get("source", "client_cam"),
                                frame_idx=int(payload.get("frame_idx", 0)),
                                plate=payload.get("plate"),
                                vehicle_data=payload.get("vehicle_data", {}),
                                telemetry=payload.get("telemetry", {}),
                                enrichment=payload.get("enrichment", {}),
                                snapshot_url=snapshot_url,
                                dispatch_ticket_id=payload.get("dispatch_ticket_id"),
                                dispatch_status=payload.get("dispatch_status", "PENDING"),
                                notes=payload.get("notes", ""),
                            )
                            session.add(row)
                        session.commit()
                    self._cloud_reachable = True
                    self._last_error = None
                    self._last_sync_ts = time.time()

                elif task_type == "plate":
                    thumb_url = payload.get("thumbnail_url")
                    if image_bytes and not thumb_url:
                        fname = f"{payload['plate']}_{int(time.time())}.jpg"
                        thumb_url = self.upload_evidence_image("plates", fname, image_bytes)
                        if thumb_url:
                            payload["thumbnail_url"] = thumb_url

                    with self.SessionLocal() as session:
                        row = PlateBacklogModel(
                            plate=payload["plate"],
                            confidence=float(payload.get("confidence", 0.0)),
                            vehicle_id=payload.get("vehicle_id"),
                            camera_id=payload.get("camera_id", "camera_01"),
                            vehicle_data=payload.get("vehicle_data", {}),
                            thumbnail_url=thumb_url,
                        )
                        session.add(row)
                        session.commit()
                    self._cloud_reachable = True
                    self._last_error = None
                    self._last_sync_ts = time.time()

                elif task_type == "vehicle":
                    with self.SessionLocal() as session:
                        plate_key = str(payload.get("plate", ""))
                        existing_v = session.get(VehicleRegistryModel, plate_key)
                        if existing_v:
                            existing_v.brand = payload.get("brand", existing_v.brand)
                            existing_v.model = payload.get("model", existing_v.model)
                            existing_v.year = int(payload.get("year", existing_v.year))
                            existing_v.color = payload.get("color", existing_v.color)
                            existing_v.fuel_type = payload.get("fuel_type", existing_v.fuel_type)
                            existing_v.is_stolen = bool(payload.get("is_stolen", existing_v.is_stolen))
                            existing_v.stolen_status = payload.get("stolen_status", existing_v.stolen_status)
                            existing_v.updated_at = datetime.now(timezone.utc)
                        else:
                            session.add(
                                VehicleRegistryModel(
                                    plate=plate_key,
                                    brand=payload.get("brand", "Desconocida"),
                                    model=payload.get("model", "Estándar"),
                                    year=int(payload.get("year", 2020)),
                                    color=payload.get("color", "Blanco"),
                                    vehicle_type=payload.get("vehicle_type", "Sedán"),
                                    fuel_type=payload.get("fuel_type", "Gasolina"),
                                    vin=payload.get("vin", ""),
                                    jurisdiction=payload.get("jurisdiction", "Ciudad de México"),
                                    owner_type=payload.get("owner_type", "Particular"),
                                    stolen_status=payload.get("stolen_status", "SIN REPORTE DE ROBO"),
                                    is_stolen=bool(payload.get("is_stolen", False)),
                                )
                            )
                        session.commit()
                    self._cloud_reachable = True
                    self._last_sync_ts = time.time()

            except Exception as e:
                self._last_error = str(e)
                logger.debug(f"Error en worker ORM de PostgreSQL: {e}")
            finally:
                self._write_queue.task_done()

    def sync_from_cloud(self, limit: int = 100) -> bool:
        """Consulta mediante SQLAlchemy ORM los últimos siniestros y placas de PostgreSQL."""
        if not self.is_configured or self.SessionLocal is None:
            return False

        try:
            with self.SessionLocal() as session:
                inc_rows = (
                    session.query(IncidentBacklogModel)
                    .order_by(desc(IncidentBacklogModel.created_at))
                    .limit(limit)
                    .all()
                )
                plate_rows = (
                    session.query(PlateBacklogModel)
                    .order_by(desc(PlateBacklogModel.created_at))
                    .limit(limit)
                    .all()
                )
                inc_dicts = [r.to_dict() for r in inc_rows]
                plate_dicts = [p.to_dict() for p in plate_rows]

            with self._lock:
                self._incidents_cache = inc_dicts
                self._plates_cache = plate_dicts

            self._cloud_reachable = True
            self._last_error = None
            self._last_sync_ts = time.time()
            return True
        except Exception as e:
            self._cloud_reachable = False
            self._last_error = str(e)
            logger.debug(f"Fallo sincronizando desde PostgreSQL con ORM: {e}")
            return False

    def get_incidents(
        self,
        limit: int = 100,
        status: Optional[str] = None,
        incident_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._incidents_cache)

        if status:
            items = [i for i in items if str(i.get("status", "")).upper() == status.upper()]
        if incident_type:
            items = [i for i in items if str(i.get("incident_type") or i.get("type") or "").lower() == incident_type.lower()]
        return items[:limit]

    def get_plates(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._plates_cache[:limit])

    def update_incident_status(
        self,
        incident_id: str,
        status: str,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        updated_item = None
        with self._lock:
            for item in self._incidents_cache:
                if str(item.get("incident_id")) == str(incident_id) or str(item.get("id")) == str(incident_id):
                    item["status"] = status.upper()
                    if notes is not None:
                        item["notes"] = notes
                    updated_item = dict(item)
                    break

        if self.is_configured and self.SessionLocal is not None and updated_item:
            try:
                with self.SessionLocal() as session:
                    row = (
                        session.query(IncidentBacklogModel)
                        .filter(IncidentBacklogModel.incident_id == updated_item["incident_id"])
                        .first()
                    )
                    if row:
                        row.status = status.upper()
                        if notes is not None:
                            row.notes = notes
                        session.commit()
            except Exception as e:
                logger.debug(f"Error actualizando estatus con ORM: {e}")

        return updated_item

    def export_csv(self, target: str = "incidents") -> str:
        output = io.StringIO()
        writer = csv.writer(output)

        if target == "plates":
            writer.writerow(["created_at", "plate", "confidence", "camera_id", "brand", "model", "fuel_type", "is_stolen", "thumbnail_url"])
            for p in self.get_plates(limit=500):
                vd = p.get("vehicle_data") or {}
                writer.writerow([
                    p.get("created_at", ""),
                    p.get("plate", ""),
                    p.get("confidence", 0.0),
                    p.get("camera_id", "camera_01"),
                    vd.get("brand", ""),
                    vd.get("model", ""),
                    vd.get("fuel_type", ""),
                    vd.get("is_stolen", False),
                    p.get("thumbnail_url", ""),
                ])
        else:
            writer.writerow([
                "incident_id",
                "created_at",
                "incident_type",
                "severity",
                "status",
                "title",
                "subtitle",
                "camera_id",
                "plate",
                "vehicle_brand_model",
                "snapshot_url",
                "notes",
            ])
            for inc in self.get_incidents(limit=500):
                vd = inc.get("vehicle_data") or inc.get("vehicle") or {}
                brand_model = f"{vd.get('brand', '')} {vd.get('model', '')}".strip()
                writer.writerow([
                    inc.get("incident_id", ""),
                    inc.get("created_at", ""),
                    inc.get("incident_type") or inc.get("type", ""),
                    inc.get("severity", "ALTO"),
                    inc.get("status", "PENDIENTE"),
                    inc.get("title", ""),
                    inc.get("subtitle", ""),
                    inc.get("camera_id", "camera_01"),
                    inc.get("plate", ""),
                    brand_model,
                    inc.get("snapshot_url", ""),
                    inc.get("notes", ""),
                ])

        return output.getvalue()

    def export_json(self) -> Dict[str, Any]:
        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "database_status": self.get_status(),
            "incidents_backlog": self.get_incidents(limit=500),
            "plates_backlog": self.get_plates(limit=500),
        }


# Instancia global singleton para todo el sistema
backlog_db = BacklogORMManager()
