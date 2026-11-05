-- =============================================================================
-- TITAN VISION // Accident-Detector - Esquema PostgreSQL para Supabase
-- Ejecuta este script en el SQL Editor de tu proyecto en Supabase.
-- =============================================================================

-- 1. Tabla principal de Backlog de Siniestros e Incidentes Viales
CREATE TABLE IF NOT EXISTS public.incidents_backlog (
    id BIGSERIAL PRIMARY KEY,
    incident_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'ALTO',
    status TEXT NOT NULL DEFAULT 'PENDIENTE',
    title TEXT NOT NULL,
    subtitle TEXT,
    camera_id TEXT NOT NULL DEFAULT 'camera_01',
    source TEXT DEFAULT 'client_cam',
    frame_idx INTEGER DEFAULT 0,
    plate TEXT,
    vehicle_data JSONB DEFAULT '{}'::jsonb,
    telemetry JSONB DEFAULT '{}'::jsonb,
    enrichment JSONB DEFAULT '{}'::jsonb,
    snapshot_url TEXT,
    dispatch_ticket_id TEXT,
    dispatch_status TEXT DEFAULT 'PENDING',
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_backlog_created_at ON public.incidents_backlog (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_backlog_type ON public.incidents_backlog (incident_type);
CREATE INDEX IF NOT EXISTS idx_incidents_backlog_status ON public.incidents_backlog (status);
CREATE INDEX IF NOT EXISTS idx_incidents_backlog_plate ON public.incidents_backlog (plate);

-- 2. Tabla de Backlog de Placas Detectadas (ALPR / OCR)
CREATE TABLE IF NOT EXISTS public.plates_backlog (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    plate TEXT NOT NULL,
    confidence NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    vehicle_id INTEGER,
    camera_id TEXT NOT NULL DEFAULT 'camera_01',
    vehicle_data JSONB DEFAULT '{}'::jsonb,
    thumbnail_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_plates_backlog_created_at ON public.plates_backlog (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plates_backlog_plate ON public.plates_backlog (plate);

-- 3. Tabla de Padrón / Registro Vehicular Personalizado
CREATE TABLE IF NOT EXISTS public.vehicles_registry (
    plate TEXT PRIMARY KEY,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    color TEXT,
    vehicle_type TEXT DEFAULT 'Sedán',
    fuel_type TEXT DEFAULT 'Gasolina',
    vin TEXT,
    jurisdiction TEXT DEFAULT 'Ciudad de México',
    owner_type TEXT DEFAULT 'Particular',
    stolen_status TEXT DEFAULT 'SIN REPORTE DE ROBO',
    is_stolen BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Bucket de Almacenamiento para Evidencias Fotográficas (Snapshots y Recortes)
INSERT INTO storage.buckets (id, name, public)
VALUES ('incident-evidence', 'incident-evidence', true)
ON CONFLICT (id) DO NOTHING;

-- 5. Políticas RLS (Row Level Security) para permitir lectura/escritura desde el Backend
ALTER TABLE public.incidents_backlog ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plates_backlog ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicles_registry ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'incidents_backlog' AND policyname = 'Allow public backend access to incidents_backlog'
    ) THEN
        CREATE POLICY "Allow public backend access to incidents_backlog"
        ON public.incidents_backlog FOR ALL
        USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'plates_backlog' AND policyname = 'Allow public backend access to plates_backlog'
    ) THEN
        CREATE POLICY "Allow public backend access to plates_backlog"
        ON public.plates_backlog FOR ALL
        USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'vehicles_registry' AND policyname = 'Allow public backend access to vehicles_registry'
    ) THEN
        CREATE POLICY "Allow public backend access to vehicles_registry"
        ON public.vehicles_registry FOR ALL
        USING (true) WITH CHECK (true);
    END IF;
END
$$;

