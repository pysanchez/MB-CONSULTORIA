-- Cuenta carteras cuyo resultado de gestión más reciente requiere seguimiento.
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
    WHERE codigo_resultado IN ('recado', 'no_contesto');
$$;

GRANT EXECUTE ON FUNCTION public.resumen_seguimientos_pendientes()
    TO service_role;
