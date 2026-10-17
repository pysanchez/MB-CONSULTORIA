-- Resume métricas en Supabase sin descargar todas las gestiones a FastAPI.
-- Los conteos son globales mientras aún no existe inicio de sesión por agente.
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
            SELECT count(DISTINCT fk_cartera)::INTEGER
            FROM public.pagos
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
