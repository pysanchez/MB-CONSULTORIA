-- Hace idempotente la carga de gestiones manuales y alinea métricas al nuevo catálogo.

ALTER TABLE public.gestiones
    ADD COLUMN IF NOT EXISTS import_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS gestiones_import_key_uidx
    ON public.gestiones (import_key);

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
            WHERE codigo_resultado = '05.-Promesa de Pago'
        ),
        'negativas_de_pago', (
            SELECT count(DISTINCT fk_cartera)::INTEGER
            FROM public.gestiones
            WHERE codigo_resultado = '20.-Negativa'
        ),
        'cuentas_con_recado', (
            SELECT count(DISTINCT fk_cartera)::INTEGER
            FROM public.gestiones
            WHERE codigo_resultado IN (
                '09.-Mnje con fam',
                '10.- Mnje trabajo',
                '11.-Mnje con ref'
            )
        ),
        'pagos_reportados', (
            SELECT count(DISTINCT reportado.fk_cartera)::INTEGER
            FROM (
                SELECT fk_cartera
                FROM public.pagos
                UNION
                SELECT fk_cartera
                FROM public.gestiones
                WHERE codigo_resultado IN (
                    '02.-Pago parcial',
                    '03.-Cuenta regularizada',
                    '12.-Liquidacion'
                )
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

CREATE OR REPLACE FUNCTION public.resumen_seguimientos_pendientes()
RETURNS INTEGER
LANGUAGE SQL
STABLE
AS $$
    WITH ultima_gestion AS (
        SELECT DISTINCT ON (fk_cartera)
            fk_cartera,
            codigo_resultado
        FROM public.gestiones
        ORDER BY fk_cartera, fecha_gestion DESC, id_gestion DESC
    )
    SELECT count(*)::INTEGER
    FROM ultima_gestion
    WHERE codigo_resultado IN (
        '01.-Sin gestion',
        '08.-Seguimiento',
        '09.-Mnje con fam',
        '10.- Mnje trabajo',
        '11.-Mnje con ref',
        '13.-No contesta',
        '14.-Buzon',
        '16.-Fuera de servicio',
        '17.-No enlaza',
        '19.-Cliente evasivo'
    );
$$;

GRANT EXECUTE ON FUNCTION public.resumen_seguimientos_pendientes()
    TO service_role;
