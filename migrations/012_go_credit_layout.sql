-- Campos que no existen en los layouts anteriores y datos propios de GO CREDIT.
-- Ejecutar una vez en Supabase antes de importar la cartera de GO CREDIT.

ALTER TABLE public.carteras
    ADD COLUMN IF NOT EXISTS referencia_pago TEXT,
    ADD COLUMN IF NOT EXISTS estatus_gestion TEXT,
    ADD COLUMN IF NOT EXISTS estatus_domi TEXT,
    ADD COLUMN IF NOT EXISTS dependencia TEXT,
    ADD COLUMN IF NOT EXISTS pago_cuota NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS monto_vencido NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS oferta_liquidacion NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS curp TEXT,
    ADD COLUMN IF NOT EXISTS entre_calles TEXT,
    ADD COLUMN IF NOT EXISTS ref4_nombre TEXT,
    ADD COLUMN IF NOT EXISTS ref4_tel TEXT,
    ADD COLUMN IF NOT EXISTS ref4_parentesco TEXT,
    ADD COLUMN IF NOT EXISTS plaza TEXT,
    ADD COLUMN IF NOT EXISTS ejecutivo TEXT,
    ADD COLUMN IF NOT EXISTS vendedor TEXT,
    ADD COLUMN IF NOT EXISTS supervisor_vendedor TEXT,
    ADD COLUMN IF NOT EXISTS banco TEXT,
    ADD COLUMN IF NOT EXISTS rango_pagado TEXT,
    ADD COLUMN IF NOT EXISTS cuotas_pagadas_rango TEXT,
    ADD COLUMN IF NOT EXISTS rango_pagado_mes_anterior TEXT,
    ADD COLUMN IF NOT EXISTS rango_pagado_30_dias TEXT,
    ADD COLUMN IF NOT EXISTS rango_pagado_15_dias TEXT;

INSERT INTO public.financieras (nombre_financiera)
SELECT 'GO CREDIT'
WHERE NOT EXISTS (
    SELECT 1
    FROM public.financieras
    WHERE upper(trim(nombre_financiera)) = 'GO CREDIT'
);
