-- Recuperación de acceso: solo el servidor y el organizador pueden emitir códigos.
BEGIN;
CREATE TABLE IF NOT EXISTS public.diapocalipsis_recovery (
    guest_id bigint PRIMARY KEY REFERENCES public.diapocalipsis_guests(id),
    requested_at timestamptz NOT NULL DEFAULT now(),
    code_hash text CHECK (code_hash ~ '^[a-f0-9]{64}$'),
    expires_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    consumed_at timestamptz
);
ALTER TABLE public.diapocalipsis_recovery ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.diapocalipsis_recovery FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.diapocalipsis_recovery TO service_role;

CREATE OR REPLACE VIEW public.diapocalipsis_recovery_pending WITH (security_invoker=true) AS
SELECT g.id AS guest_id, g.name, g.email, r.requested_at, r.expires_at
FROM public.diapocalipsis_recovery r JOIN public.diapocalipsis_guests g ON g.id=r.guest_id
WHERE r.consumed_at IS NULL;
REVOKE ALL ON public.diapocalipsis_recovery_pending FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.diapocalipsis_recovery_pending TO service_role;

CREATE OR REPLACE FUNCTION public.diapocalipsis_request_recovery(p_email text, p_code_hash text)
RETURNS boolean LANGUAGE plpgsql SET search_path='' AS $$
DECLARE gid bigint; old public.diapocalipsis_recovery%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext(lower(btrim(p_email))));
    SELECT id INTO gid FROM public.diapocalipsis_guests WHERE email=lower(btrim(p_email));
    IF gid IS NULL THEN RETURN false; END IF;
    SELECT * INTO old FROM public.diapocalipsis_recovery WHERE guest_id=gid FOR UPDATE;
    IF FOUND AND old.consumed_at IS NULL AND
        (old.expires_at > now() OR old.requested_at + INTERVAL '60 seconds' > now()) THEN
        RETURN false;
    END IF;
    INSERT INTO public.diapocalipsis_recovery(guest_id,requested_at,code_hash,expires_at,attempts,consumed_at)
    VALUES(gid,now(),p_code_hash,CASE WHEN p_code_hash IS NOT NULL THEN now()+INTERVAL '15 minutes' ELSE NULL END,0,NULL)
    ON CONFLICT(guest_id) DO UPDATE SET requested_at=EXCLUDED.requested_at,code_hash=EXCLUDED.code_hash,
        expires_at=EXCLUDED.expires_at,attempts=0,consumed_at=NULL;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.diapocalipsis_issue_recovery(p_email text, p_code_hash text)
RETURNS boolean LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
    IF p_code_hash IS NULL OR p_code_hash !~ '^[a-f0-9]{64}$' THEN RETURN false; END IF;
    UPDATE public.diapocalipsis_recovery SET code_hash=p_code_hash,expires_at=now()+INTERVAL '15 minutes',attempts=0,consumed_at=NULL
    WHERE guest_id=(SELECT id FROM public.diapocalipsis_guests WHERE email=lower(btrim(p_email)));
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.diapocalipsis_finish_recovery(p_email text,p_code_hash text,p_token_hash text)
RETURNS boolean LANGUAGE plpgsql SET search_path='' AS $$
DECLARE r public.diapocalipsis_recovery%ROWTYPE;
BEGIN
    SELECT rec.* INTO r FROM public.diapocalipsis_recovery rec JOIN public.diapocalipsis_guests g ON g.id=rec.guest_id
    WHERE g.email=lower(btrim(p_email)) FOR UPDATE OF rec;
    IF NOT FOUND OR r.code_hash IS NULL OR r.expires_at IS NULL OR r.expires_at<=now() OR r.attempts>=5 OR r.consumed_at IS NOT NULL THEN
        RETURN false;
    END IF;
    IF r.code_hash IS DISTINCT FROM p_code_hash THEN
        UPDATE public.diapocalipsis_recovery SET attempts=attempts+1 WHERE guest_id=r.guest_id;
        RETURN false;
    END IF;
    UPDATE public.diapocalipsis_guests SET token_hash=p_token_hash WHERE id=r.guest_id;
    UPDATE public.diapocalipsis_recovery SET code_hash=NULL,consumed_at=now() WHERE guest_id=r.guest_id;
    RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.diapocalipsis_request_recovery(text,text),
    public.diapocalipsis_issue_recovery(text,text), public.diapocalipsis_finish_recovery(text,text,text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.diapocalipsis_request_recovery(text,text),
    public.diapocalipsis_issue_recovery(text,text), public.diapocalipsis_finish_recovery(text,text,text)
    TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
