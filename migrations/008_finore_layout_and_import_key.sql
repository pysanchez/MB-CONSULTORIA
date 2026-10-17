-- Campos del layout FINORE y clave estable para importar cada financiera.
-- La clave usa No. de Crédito cuando existe (BORDER CREDIT) y, si no existe,
-- IdCuenta (FINORE), sin copiar un dato al campo semántico del otro.

ALTER TABLE public.carteras
    ADD COLUMN IF NOT EXISTS clave_importacion TEXT,
    ADD COLUMN IF NOT EXISTS cartera_campa TEXT,
    ADD COLUMN IF NOT EXISTS cartera TEXT,
    ADD COLUMN IF NOT EXISTS frecuencia_detalle TEXT,
    ADD COLUMN IF NOT EXISTS fecha_arranque DATE,
    ADD COLUMN IF NOT EXISTS pagos_ago NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS pagos_jul NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS monto_ult_pago_finore NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS pagos_ptes INTEGER,
    ADD COLUMN IF NOT EXISTS pagos_pdtes_actual INTEGER,
    ADD COLUMN IF NOT EXISTS erogacion NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS pago_mensual NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS edad INTEGER,
    ADD COLUMN IF NOT EXISTS sucursal TEXT,
    ADD COLUMN IF NOT EXISTS gestiones INTEGER,
    ADD COLUMN IF NOT EXISTS ventanilla TEXT;

ALTER TABLE public.carteras
    ALTER COLUMN numero_credito DROP NOT NULL;

UPDATE public.carteras
SET clave_importacion = COALESCE(numero_credito, id_cuenta)
WHERE clave_importacion IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.carteras
        WHERE clave_importacion IS NOT NULL
        GROUP BY fk_financiera, clave_importacion
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Hay claves de importación duplicadas por financiera. Resuélvelas antes de aplicar esta migración.';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS carteras_financiera_clave_importacion_uidx
    ON public.carteras (fk_financiera, clave_importacion);
