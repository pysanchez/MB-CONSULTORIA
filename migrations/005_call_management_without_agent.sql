-- Permite registrar llamadas antes de que haya agentes con inicio de sesión.
ALTER TABLE public.gestiones
    ALTER COLUMN fk_agente DROP NOT NULL;

CREATE INDEX IF NOT EXISTS gestiones_cartera_fecha_idx
    ON public.gestiones (fk_cartera, fecha_gestion DESC);

-- Mantiene en la cuenta el último resultado, cantidad de gestiones y promesa.
CREATE OR REPLACE FUNCTION public.actualizar_resumen_cartera_despues_de_gestion()
RETURNS TRIGGER
LANGUAGE PLPGSQL
AS $$
BEGIN
    UPDATE public.carteras AS cartera
    SET gestiones = coalesce(cartera.gestiones, 0) + 1,
        ult_gestion = NEW.codigo_resultado,
        fecha_prom = coalesce(NEW.fecha_promesa, cartera.fecha_prom),
        monto_prom = coalesce(NEW.monto_promesa, cartera.monto_prom)
    WHERE cartera.id_cartera = NEW.fk_cartera;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS gestiones_actualizar_resumen_cartera
    ON public.gestiones;

CREATE TRIGGER gestiones_actualizar_resumen_cartera
AFTER INSERT ON public.gestiones
FOR EACH ROW
EXECUTE FUNCTION public.actualizar_resumen_cartera_despues_de_gestion();

-- Un pago reportado durante una llamada también cuenta en el resumen,
-- aunque el registro financiero detallado se capture más adelante.
CREATE OR REPLACE FUNCTION public.resumen_dashboard_general(
    p_inicio_ayer TIMESTAMP WITHOUT TIME ZONE,
    p_inicio_hoy TIMESTAMP WITHOUT TIME ZONE
)
RETURNS JSONB
LANGUAGE SQL
STABLE
AS $$
    SELECT jsonb_build_object(
        'cuentas_en_cartera', (
            SELECT count(*)::INTEGER
            FROM public.carteras
        ),
        'llamadas_ayer', (
            SELECT count(*)::INTEGER
            FROM public.gestiones
            WHERE fecha_gestion >= p_inicio_ayer
              AND fecha_gestion < p_inicio_hoy
              AND tipo_contacto ILIKE '%llamada%'
        ),
        'llamadas_acumuladas', (
            SELECT count(*)::INTEGER
            FROM public.gestiones
            WHERE tipo_contacto ILIKE '%llamada%'
        ),
        'cuentas_promesadas', (
            SELECT count(DISTINCT fk_cartera)::INTEGER
            FROM public.gestiones
            WHERE estatus_contacto ILIKE '%promesa%'
               OR codigo_resultado ILIKE '%promesa%'
        ),
        'negativas_de_pago', (
            SELECT count(DISTINCT fk_cartera)::INTEGER
            FROM public.gestiones
            WHERE estatus_contacto ILIKE '%negativa%'
               OR codigo_resultado ILIKE '%negativa%'
        ),
        'cuentas_con_recado', (
            SELECT count(DISTINCT fk_cartera)::INTEGER
            FROM public.gestiones
            WHERE estatus_contacto ILIKE '%recado%'
               OR codigo_resultado ILIKE '%recado%'
        ),
        'pagos_reportados', (
            SELECT count(DISTINCT reportado.fk_cartera)::INTEGER
            FROM (
                SELECT fk_cartera
                FROM public.pagos
                UNION
                SELECT fk_cartera
                FROM public.gestiones
                WHERE codigo_resultado = 'pago_reportado'
            ) AS reportado
        ),
        'cuentas_con_gestion', (
            SELECT count(DISTINCT fk_cartera)::INTEGER
            FROM public.gestiones
        )
    );
$$;

GRANT EXECUTE ON FUNCTION public.resumen_dashboard_general(
    TIMESTAMP WITHOUT TIME ZONE,
    TIMESTAMP WITHOUT TIME ZONE
) TO service_role;
