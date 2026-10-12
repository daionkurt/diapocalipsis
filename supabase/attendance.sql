-- Existing registrations keep their presentation status.
ALTER TABLE public.diapocalipsis_guests ADD COLUMN IF NOT EXISTS is_presenter boolean NOT NULL DEFAULT true;
NOTIFY pgrst, 'reload schema';
