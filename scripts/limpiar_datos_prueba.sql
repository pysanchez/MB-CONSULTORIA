-- Elimina datos operativos de prueba de pagos, gestiones y carteras.
-- Conserva los catálogos de financieras y agentes.
-- Este archivo es una limpieza manual, no una migración de esquema.

BEGIN;

DELETE FROM public.pagos;
DELETE FROM public.gestiones;
DELETE FROM public.carteras;

COMMIT;
