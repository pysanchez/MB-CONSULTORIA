-- Ajusta una instalación que ya aplicó la migración 001 con el mapeo anterior.
-- También es seguro correrla después de la versión corregida de 001.

ALTER TABLE public.carteras
    ADD COLUMN IF NOT EXISTS numero_credito TEXT;

DROP INDEX IF EXISTS public.carteras_financiera_id_cuenta_uidx;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'carteras'
          AND column_name = 'clave_cliente'
    ) THEN
        EXECUTE $migration$
            UPDATE public.carteras
            SET numero_credito = id_cuenta,
                id_cuenta = COALESCE(NULLIF(clave_cliente, ''), id_cuenta)
            WHERE numero_credito IS NULL
        $migration$;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.carteras
        WHERE numero_credito IS NOT NULL
        GROUP BY fk_financiera, numero_credito
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Hay números de crédito duplicados dentro de una financiera. Resuélvelos antes de continuar.';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS carteras_financiera_numero_credito_uidx
    ON public.carteras (fk_financiera, numero_credito);

