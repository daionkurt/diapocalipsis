-- Una entrega por expediente/correo. Conserva los archivos y claves existentes.
BEGIN;
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
