-- Amplía identificadores y teléfonos para aceptar los valores del Excel de
-- BORDER CREDIT, que pueden superar el límite de varchar(20).

ALTER TABLE public.carteras
    ALTER COLUMN numero_credito TYPE TEXT,
    ALTER COLUMN celular TYPE TEXT,
    ALTER COLUMN casa TYPE TEXT,
    ALTER COLUMN ref1_tel TYPE TEXT,
    ALTER COLUMN ref2_tel TYPE TEXT;
