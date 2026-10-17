-- Campos adicionales del layout actualizado de BORDER CREDIT.
-- Ejecutar una vez en el SQL Editor de Supabase antes de importar ese archivo.

ALTER TABLE public.carteras
    ADD COLUMN IF NOT EXISTS fecha_asig DATE,
    ADD COLUMN IF NOT EXISTS telempresa_alterno TEXT,
    ADD COLUMN IF NOT EXISTS correo_empresa_alterno TEXT,
    ADD COLUMN IF NOT EXISTS estatus_correo_empresa_2 TEXT,
    ADD COLUMN IF NOT EXISTS opcion_1_pago_unico NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS ahorro_cliente NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS porcentaje_descuento NUMERIC(7, 2),
    ADD COLUMN IF NOT EXISTS opcion_2_convenio_total NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS abono_semanal NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS numero_semanas INTEGER,
    ADD COLUMN IF NOT EXISTS oferta_especial_propuesta TEXT,
    ADD COLUMN IF NOT EXISTS vigencia TEXT;
