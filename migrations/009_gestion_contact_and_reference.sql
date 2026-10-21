-- Registra a quién se llamó y permite agregar una tercera referencia por cuenta.

ALTER TABLE public.gestiones
    ADD COLUMN IF NOT EXISTS persona_contactada TEXT,
    ADD COLUMN IF NOT EXISTS telefono_contactado TEXT;

ALTER TABLE public.carteras
    ADD COLUMN IF NOT EXISTS ref3_nombre TEXT,
    ADD COLUMN IF NOT EXISTS ref3_tel TEXT,
    ADD COLUMN IF NOT EXISTS ref3_parentesco TEXT,
    ADD COLUMN IF NOT EXISTS ref3_domicilio TEXT;

CREATE INDEX IF NOT EXISTS gestiones_resultado_fecha_idx
    ON public.gestiones (fk_cartera, codigo_resultado, fecha_gestion DESC);

CREATE INDEX IF NOT EXISTS gestiones_fecha_idx
    ON public.gestiones (fecha_gestion DESC);
