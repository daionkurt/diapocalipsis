-- Allow explicitly removing the current file while keeping one active file per email.
CREATE OR REPLACE FUNCTION public.diapocalipsis_single_submission()
RETURNS trigger LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF OLD.file_path IS NOT NULL AND NEW.file_path IS NULL AND NEW.filename IS NULL
        AND NEW.file_bucket IS NULL AND NEW.email IS NOT DISTINCT FROM OLD.email THEN
        RETURN NEW;
    END IF;
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
NOTIFY pgrst, 'reload schema';
