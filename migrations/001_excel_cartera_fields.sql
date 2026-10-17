-- MB CONSULTORIA: campos del layout Excel para la tabla carteras.
-- Ejecuta este script una sola vez en el SQL Editor de Supabase antes de importar.

ALTER TABLE public.carteras
    ADD COLUMN IF NOT EXISTS numero_credito TEXT,
    ADD COLUMN IF NOT EXISTS prioridad TEXT,
    ADD COLUMN IF NOT EXISTS excel_pagos TEXT,
    ADD COLUMN IF NOT EXISTS empresa_pagadora TEXT,
    ADD COLUMN IF NOT EXISTS telempresa TEXT,
    ADD COLUMN IF NOT EXISTS correo_empresa TEXT,
    ADD COLUMN IF NOT EXISTS estatus_correo_empresa TEXT,
    ADD COLUMN IF NOT EXISTS referencia_1 TEXT,
    ADD COLUMN IF NOT EXISTS ref1_tipo_telefono TEXT,
    ADD COLUMN IF NOT EXISTS referencia_2 TEXT,
    ADD COLUMN IF NOT EXISTS en_predic TEXT,
    ADD COLUMN IF NOT EXISTS ref2_tipo_telefono TEXT,
    ADD COLUMN IF NOT EXISTS producto TEXT,
    ADD COLUMN IF NOT EXISTS dias_atraso_estimado TEXT,
    ADD COLUMN IF NOT EXISTS pagos_atrasados_jun TEXT,
    ADD COLUMN IF NOT EXISTS deudas_vencidas_toku NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS capital_vencido NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS intereses_vencidos NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS moratorios NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS pagado_agosto NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS saldo_estimado_3108 NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS tramo TEXT,
    ADD COLUMN IF NOT EXISTS marca_interna TEXT,
    ADD COLUMN IF NOT EXISTS correo_cliente TEXT,
    ADD COLUMN IF NOT EXISTS estatus_correo_cliente TEXT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.carteras
        WHERE numero_credito IS NOT NULL
        GROUP BY fk_financiera, numero_credito
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Hay números de crédito duplicados dentro de una financiera. Resuélvelas antes de crear el índice de importación.';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS carteras_financiera_numero_credito_uidx
    ON public.carteras (fk_financiera, numero_credito);

