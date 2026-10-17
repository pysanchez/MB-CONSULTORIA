# MB CONSULTORIA CRM

API local en FastAPI para conectar la interfaz con Supabase e importar las carteras de Excel.

## Preparación

1. Crea y activa un entorno virtual: `python -m venv .venv`.
2. Instala las dependencias: `pip install -r requirements.txt`.
3. Completa `SUPABASE_URL` y `SUPABASE_SECRET_KEY` en `.env`.
4. Ejecuta, en orden, las migraciones `001_excel_cartera_fields.sql`, `002_separate_credit_number.sql`, `003_search_and_seed_financials.sql`, `004_general_dashboard_metrics.sql` y `005_call_management_without_agent.sql` desde el SQL Editor de Supabase.
5. Inicia la API: `python main.py`.
6. Sirve la carpeta con Live Server en el puerto 5500 y abre la página. La API también documenta sus rutas en `http://127.0.0.1:8000/docs`.

La secret key debe permanecer solo en el backend. No la incluyas en HTML, CSS ni JavaScript del navegador.

## Rutas disponibles

- `GET /api/health`: comprueba acceso a `financieras`.
- `GET /api/financieras`: lista las financieras para el selector de carga.
- `GET /api/agentes`: lista los agentes registrados.
- `GET /api/carteras`: lista o busca cuentas por crédito, teléfonos o palabras parciales del nombre; admite filtros y paginación en Supabase.
- `GET /api/dashboard/general`: devuelve el resumen global de cuentas, llamadas, promesas, negativas, recados y pagos mientras no existe autenticación por agente.
- `GET /api/dashboard/{fk_agente}`: devuelve las mismas métricas para un agente registrado.
- `GET /api/carteras/{fk_cartera}/gestiones`: devuelve el historial paginado de una cuenta.
- `POST /api/gestiones`: registra una llamada y su resultado para una cuenta.
- `POST /api/carteras/importar`: valida el layout y crea o actualiza cuentas en `carteras`.

## Importación de la cartera

El importador busca el encabezado en las primeras 30 filas y valida las columnas de anclaje del layout compartido. Lee los datos por posición para diferenciar los encabezados repetidos. Acepta `.xlsx`, `.xls`, `.xlsm` y `.csv`, con un máximo de 25 MB y 10,000 cuentas por archivo. La migración 003 registra BORDER CREDIT y FINORE para que aparezcan en el selector.

`Clave Cliente` se guarda en `carteras.id_cuenta` y `No. de Crédito` en `carteras.numero_credito`; ambos permanecen como identificadores distintos. El selector asigna la financiera y, opcionalmente, un agente. El agente que venga en el libro se conserva en `agente_texto`.

La carga hace upsert con la combinación `fk_financiera + numero_credito`, por lo que una nueva versión del mismo archivo actualiza esas cuentas en lugar de duplicarlas. Se envían todos los campos del layout; una celda vacía reemplaza el dato anterior con `NULL`. El agente ficticio de la interfaz no se guarda ni se envía a Supabase. La migración agrega columnas para los datos que no estaban en la tabla y un índice único para ese par. Si ya hay duplicados en Supabase, la migración se detiene y hay que resolverlos primero. La carga se procesa en lotes; si un lote falla, la respuesta indica cuántas filas alcanzó a guardar, y se puede volver a cargar el archivo después de corregir el problema.

La búsqueda utiliza la función SQL `buscar_carteras` para consultar coincidencias en la base de datos y entrega páginas de resultados. En nombres, busca cada palabra introducida, así que permite buscar por uno o varios nombres o apellidos sin importar que solo se escriba una parte.

El resumen de inicio utiliza `resumen_dashboard_general` para calcular las métricas directamente en Supabase. La sección “Mi cartera” muestra temporalmente la cartera general y pagina las cuentas; al agregar inicio de sesión, se podrá filtrar por agente.

La vista “Registrar gestión” permite buscar una cuenta, guardar el resultado y comentario de una llamada y consultar su historial. Las promesas solicitan fecha y monto. Mientras no exista login, las gestiones se guardan con `fk_agente = NULL`; la migración 005 habilita ese flujo y actualiza en la cuenta el total y el último resultado de gestión.

Las métricas de gestión buscan `llamada`, `promesa`, `negativa` y `recado` en los campos de tipo y resultado. Conviene usar esos términos consistentemente al guardar las gestiones.

Este backend todavía no tiene autenticación. Mantenlo en local; antes de exponerlo o desplegarlo hay que implementar autenticación y autorización por agente. La secret key del servidor tiene privilegios elevados en Supabase.

