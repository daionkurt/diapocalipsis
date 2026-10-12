-- Diapocalipsis: ejecutar una vez en SQL Editor del proyecto de Supabase.
-- Los registros solo se acceden desde el servidor de Streamlit con una Secret API key.
BEGIN;

CREATE TABLE IF NOT EXISTS public.diapocalipsis_guests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (char_length(trim(name)) BETWEEN 2 AND 80),
    email text NOT NULL UNIQUE CHECK (email = lower(trim(email)) AND char_length(email) <= 254),
    topic text NOT NULL CHECK (char_length(trim(topic)) BETWEEN 3 AND 160),
    -- Compatibilidad con registros previos; este campo ya no se usa en la app.
    category text NOT NULL DEFAULT 'Otro misterio' CHECK (category IN ('Conspiraciones','Sucesos paranormales','Seres de otros mundos','Monstruos y leyendas','Otro misterio')),
    token_hash text NOT NULL CHECK (token_hash ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    position bigint CHECK (position > 0),
    presented boolean NOT NULL DEFAULT false,
    filename text,
    file_path text,
    file_bucket text,
    CHECK ((filename IS NULL AND file_path IS NULL AND file_bucket IS NULL)
        OR (filename IS NOT NULL AND file_path IS NOT NULL AND file_bucket IS NOT NULL))
);

ALTER TABLE public.diapocalipsis_guests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.diapocalipsis_guests FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.diapocalipsis_guests TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.diapocalipsis_guests_id_seq TO service_role;

-- Sin políticas públicas de lectura/escritura para invitados; la app verifica sus claves privadas.
-- El bucket se crea PRIVADO. El script no vacía ni borra archivos.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('presentaciones', 'presentaciones', false, 52428800,
    ARRAY['application/pdf', 'application/octet-stream', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'])
ON CONFLICT (id) DO UPDATE SET
    allowed_mime_types = EXCLUDED.allowed_mime_types,
    file_size_limit = GREATEST(storage.buckets.file_size_limit, EXCLUDED.file_size_limit);

CREATE OR REPLACE FUNCTION public.diapocalipsis_validate_evidence()
RETURNS trigger LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    changed_file boolean;
BEGIN
    IF TG_OP = 'INSERT' THEN
        changed_file := NEW.file_path IS NOT NULL;
    ELSE
        changed_file := NEW.file_path IS NOT NULL AND
            (NEW.file_path IS DISTINCT FROM OLD.file_path OR NEW.file_bucket IS DISTINCT FROM OLD.file_bucket);
    END IF;
    IF changed_file THEN
        IF now() >= TIMESTAMPTZ '2026-10-23 12:00:00 America/Mexico_City' THEN
            RAISE EXCEPTION 'La recepción de evidencia ha cerrado';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM storage.objects o JOIN storage.buckets b ON b.id = o.bucket_id
            WHERE o.bucket_id = NEW.file_bucket AND o.name = NEW.file_path AND b.public = false
        ) THEN
            RAISE EXCEPTION 'La evidencia debe existir en un bucket privado';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.diapocalipsis_validate_evidence() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.diapocalipsis_validate_evidence() TO service_role;

CREATE OR REPLACE TRIGGER diapocalipsis_evidence_guard
BEFORE INSERT OR UPDATE ON public.diapocalipsis_guests
FOR EACH ROW EXECUTE FUNCTION public.diapocalipsis_validate_evidence();

CREATE OR REPLACE FUNCTION public.diapocalipsis_single_submission()
RETURNS trigger LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF OLD.file_path IS NOT NULL AND (
        NEW.file_path IS DISTINCT FROM OLD.file_path OR
        NEW.file_bucket IS DISTINCT FROM OLD.file_bucket OR
        NEW.filename IS DISTINCT FROM OLD.filename OR
        NEW.email IS DISTINCT FROM OLD.email
    ) THEN
        RAISE EXCEPTION 'Este correo ya entregó su documento' USING ERRCODE = 'P0002';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.diapocalipsis_single_submission() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.diapocalipsis_single_submission() TO service_role;
CREATE OR REPLACE TRIGGER diapocalipsis_single_submission_guard
BEFORE UPDATE ON public.diapocalipsis_guests
FOR EACH ROW EXECUTE FUNCTION public.diapocalipsis_single_submission();

COMMIT;
