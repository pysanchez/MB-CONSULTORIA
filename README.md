# MB CONSULTORIA CRM

CRM en FastAPI para servir la interfaz, conectar con Supabase e importar carteras de Excel.

## Preparación

1. Crea y activa un entorno virtual: `python -m venv .venv`.
2. Instala las dependencias: `pip install -r requirements.txt`.
3. Copia `.env.example` como `.env` y completa `SUPABASE_URL` y `SUPABASE_SECRET_KEY`.
4. Ejecuta, en orden, las migraciones `001_excel_cartera_fields.sql` a `010_pending_followups_metric.sql` desde el SQL Editor de Supabase.
5. Inicia la API: `python main.py`.
6. Sirve la carpeta con Live Server en el puerto 5500 y abre la página. La API también documenta sus rutas en `http://127.0.0.1:8000/docs`.

La secret key debe permanecer solo en el backend. No la incluyas en HTML, CSS ni JavaScript del navegador.

## Rutas disponibles

- `GET /api/health`: comprueba acceso a `financieras`.
- `POST /api/auth/login` y `POST /api/auth/logout`: abren y cierran la sesión del CRM.
- `GET /api/financieras`: lista las financieras para el selector de carga.
- `GET /api/agentes`: lista los agentes registrados.
- `GET /api/carteras`: lista o busca cuentas por crédito, teléfonos o palabras parciales del nombre; admite filtros y paginación en Supabase.
- `GET /api/carteras/por-numero-credito`: busca coincidencias exactas para abrir desde NBX/VICIdial.
- `GET /api/dashboard/general`: devuelve el resumen global de cuentas, llamadas, promesas, negativas, recados y pagos mientras no existe autenticación por agente.
- `GET /api/dashboard/{fk_agente}`: devuelve las mismas métricas para un agente registrado.
- `GET /api/gestiones/hoy`: lista las últimas gestiones del día local.
- `GET /api/reportes/gestiones.xlsx`: descarga un Excel filtrable por fecha y resultado.
- `GET /api/carteras/{fk_cartera}/gestiones`: devuelve el historial paginado de una cuenta.
- `POST /api/gestiones`: registra una llamada y su resultado para una cuenta.
- `POST /api/carteras/{fk_cartera}/referencias`: agrega la tercera referencia de una cuenta.
- `POST /api/carteras/importar`: valida el layout, agrega cuentas nuevas y omite claves ya existentes.

## Importación de la cartera

El importador usa pandas para leer Excel y CSV, busca encabezados en las primeras 30 filas y conecta las columnas con sus campos de Supabase por nombre normalizado, aunque cambie su orden. Los encabezados repetidos de referencias, frecuencia y estatus de correo se asignan por orden de aparición. FINORE identifica cada cuenta con `IdCuenta`; BORDER CREDIT usa su `No. de Crédito`. Se conservan en columnas distintas y cada una tiene una clave de importación adecuada. Acepta `.xlsx`, `.xls`, `.xlsm` y `.csv`, con un máximo de 25 MB y 10,000 cuentas por archivo. La migración 003 registra BORDER CREDIT y FINORE para que aparezcan en el selector.

`Clave Cliente` se guarda en `carteras.id_cuenta` y `No. de Crédito` en `carteras.numero_credito`; ambos permanecen como identificadores distintos. El selector asigna la financiera y, opcionalmente, un agente. El agente que venga en el libro se conserva en `agente_texto`.

La carga inserta en lotes usando el índice único `fk_financiera + clave_importacion`. Si una cuenta ya existe para esa financiera, Supabase la omite y conserva los datos guardados. La respuesta informa cuántas cuentas nuevas agregó y cuántas omitió. Las cuentas nuevas envían los campos mapeados del layout; las celdas vacías se guardan como `NULL`. El inicio muestra el total de cuentas y el conteo separado de BORDER CREDIT y FINORE.

La búsqueda utiliza la función SQL `buscar_carteras` para consultar coincidencias en la base de datos y entrega páginas de resultados. En nombres, busca cada palabra introducida, así que permite buscar por uno o varios nombres o apellidos sin importar que solo se escriba una parte.

El resumen de inicio utiliza `resumen_dashboard_general` para calcular las métricas directamente en Supabase. La sección “Mi cartera” muestra temporalmente la cartera general y pagina las cuentas; se podrá filtrar por agente cuando haya cuentas individuales.

La vista “Registrar gestión” permite buscar una cuenta, seleccionar a quién se llamó, guardar el resultado y comentario, filtrar el historial y consultar su detalle. También permite agregar una tercera referencia a la cuenta. Las promesas solicitan fecha y monto. Mientras no exista login por agente, las gestiones se guardan con `fk_agente = NULL`; las migraciones 005 y 009 habilitan ese flujo y almacenan la persona contactada. El inicio muestra gestiones de hoy, actualiza métricas cada minuto y combina recados con llamadas no contestadas cuyo último resultado requiere seguimiento. La vista “Reportes” descarga gestiones filtradas por fecha y resultado en Excel.

Las métricas de gestión buscan `llamada`, `promesa`, `negativa` y `recado` en los campos de tipo y resultado. Conviene usar esos términos consistentemente al guardar las gestiones.

## Integración con NBX/VICIdial

El CRM acepta `?credito=NUMERO` en su URL. Tras iniciar sesión, busca ese número de crédito directamente en Supabase y abre la cuenta si hay una sola coincidencia. Si aparece en más de una financiera, muestra las opciones para elegir.

En la campaña de VICIdial (por ejemplo, la 005), configura el campo Web Form con una URL como:

```text
VARhttps://mb-consultoria.onrender.com/?credito=--A--vendor_lead_code--B--
```

Este ejemplo supone que `vendor_lead_code` contiene el número de crédito. Si NBX lo guarda en otro campo, usa el marcador de ese campo, como `user_custom_one`. Configura el Web Form para abrir en una pestaña o ventana principal si esa opción está disponible; así el CRM conserva su sesión de inicio. La documentación de VICIdial describe el prefijo `VAR` y los marcadores `--A--campo--B--`.

## Despliegue en Render

El archivo `render.yaml` configura un solo servicio web que sirve la página y la API bajo el mismo dominio. Render instala `requirements.txt` y ejecuta Uvicorn en el puerto que proporciona mediante `PORT`.

1. En Render, crea un Blueprint desde el repositorio y selecciona `render.yaml`.
2. Cuando Render lo solicite, agrega `SUPABASE_URL` y `SUPABASE_SECRET_KEY` como variables secretas.
3. Define `CRM_ACCESS_PASSWORD` como una contraseña aleatoria de al menos 32 caracteres. Guárdala en un administrador de contraseñas y compártela solo con el equipo.
4. Render genera `SESSION_SECRET` automáticamente. No cambies ni publiques ese valor.
5. Completa la creación del servicio y abre su URL. La pantalla de acceso pedirá la contraseña del despacho.

En producción la API exige la sesión; la cookie es `HttpOnly`, segura y vence después de ocho horas. El servicio falla al iniciar si faltan la contraseña o el secreto de sesión. El acceso local sigue abierto si no defines `CRM_ACCESS_PASSWORD` en `.env`.

Esta contraseña es compartida y todavía no identifica agentes ni asigna permisos por usuario. Úsala para pruebas del despacho; antes de operar con cuentas individuales, habrá que integrar autenticación por agente y limitar el acceso a la cartera asignada. `SUPABASE_SECRET_KEY` permanece solamente en el backend y debe configurarse en el entorno de Render, nunca en el navegador ni en Git.

