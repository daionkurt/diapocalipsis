-- Actualiza el cierre al viernes 23 de octubre, 5:00 p.m.
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
        IF now() >= TIMESTAMPTZ '2026-10-23 17:00:00 America/Mexico_City' THEN
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
