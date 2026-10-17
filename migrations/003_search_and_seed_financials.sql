-- Registra las dos financieras que usa MB CONSULTORIA sin duplicarlas.
INSERT INTO public.financieras (nombre_financiera)
SELECT requested.nombre
FROM (VALUES ('BORDER CREDIT'), ('FINORE')) AS requested(nombre)
WHERE NOT EXISTS (
    SELECT 1
    FROM public.financieras AS existing
    WHERE upper(trim(existing.nombre_financiera)) = requested.nombre
);

-- Busca en Supabase y pagina los resultados sin descargar la cartera completa.
-- En nombres, cada palabra buscada debe aparecer en el nombre del cliente,
-- aunque se escriban solo nombres o solo apellidos.
CREATE OR REPLACE FUNCTION public.buscar_carteras(
    p_buscar TEXT,
    p_fk_agente INTEGER DEFAULT NULL,
    p_fk_financiera INTEGER DEFAULT NULL,
    p_limite INTEGER DEFAULT 51,
    p_desde INTEGER DEFAULT 0
)
RETURNS SETOF public.carteras
LANGUAGE SQL
STABLE
AS $$
    SELECT cartera.*
    FROM public.carteras AS cartera
    WHERE (p_fk_agente IS NULL OR cartera.fk_agente = p_fk_agente)
      AND (p_fk_financiera IS NULL OR cartera.fk_financiera = p_fk_financiera)
      AND (
          strpos(lower(coalesce(cartera.id_cuenta, '')), lower(trim(p_buscar))) > 0
          OR strpos(lower(coalesce(cartera.numero_credito, '')), lower(trim(p_buscar))) > 0
          OR strpos(lower(coalesce(cartera.celular, '')), lower(trim(p_buscar))) > 0
          OR strpos(lower(coalesce(cartera.casa, '')), lower(trim(p_buscar))) > 0
          OR strpos(lower(coalesce(cartera.ref1_tel, '')), lower(trim(p_buscar))) > 0
          OR strpos(lower(coalesce(cartera.ref2_tel, '')), lower(trim(p_buscar))) > 0
          OR (
              coalesce(trim(p_buscar), '') <> ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM unnest(regexp_split_to_array(lower(trim(p_buscar)), '\s+')) AS token
                  WHERE strpos(lower(coalesce(cartera.cliente, '')), token) = 0
              )
          )
      )
    ORDER BY cartera.id_cartera
    LIMIT greatest(1, least(p_limite, 101))
    OFFSET greatest(p_desde, 0);
$$;

GRANT EXECUTE ON FUNCTION public.buscar_carteras(TEXT, INTEGER, INTEGER, INTEGER, INTEGER)
    TO service_role;
