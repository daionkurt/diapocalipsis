BEGIN;
CREATE TABLE IF NOT EXISTS public.diapocalipsis_roulette (
    id integer PRIMARY KEY CHECK(id=1), drawn bigint[] NOT NULL DEFAULT '{}', selected bigint
);
INSERT INTO public.diapocalipsis_roulette(id) VALUES(1) ON CONFLICT DO NOTHING;
ALTER TABLE public.diapocalipsis_roulette ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.diapocalipsis_roulette FROM PUBLIC,anon,authenticated;
GRANT SELECT,UPDATE ON public.diapocalipsis_roulette TO service_role;
CREATE OR REPLACE FUNCTION public.diapocalipsis_draw()
RETURNS bigint LANGUAGE plpgsql SET search_path='' AS $$
DECLARE picked bigint; seen bigint[];
BEGIN
    SELECT drawn INTO seen FROM public.diapocalipsis_roulette WHERE id=1 FOR UPDATE;
    SELECT id INTO picked FROM public.diapocalipsis_guests
    WHERE is_presenter AND filename IS NOT NULL AND NOT(id=ANY(seen)) ORDER BY random() LIMIT 1;
    IF picked IS NULL THEN RETURN NULL; END IF;
    UPDATE public.diapocalipsis_roulette SET drawn=array_append(drawn,picked),selected=picked WHERE id=1;
    RETURN picked;
END;
$$;
CREATE OR REPLACE FUNCTION public.diapocalipsis_reset_roulette()
RETURNS void LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
    UPDATE public.diapocalipsis_roulette SET drawn='{}',selected=NULL WHERE id=1;
END;
$$;
REVOKE ALL ON FUNCTION public.diapocalipsis_draw(),public.diapocalipsis_reset_roulette() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.diapocalipsis_draw(),public.diapocalipsis_reset_roulette() TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
