# MB CONSULTORIA CRM

CRM en FastAPI para servir la interfaz, conectar con Supabase e importar carteras de Excel.

## Preparación

1. Crea y activa un entorno virtual: `python -m venv .venv`.
2. Instala las dependencias: `pip install -r requirements.txt`.
3. Copia `.env.example` como `.env` y completa `SUPABASE_URL` y `SUPABASE_SECRET_KEY`.
4. Ejecuta, en orden, las migraciones `001_excel_cartera_fields.sql` a `011_management_import.sql` desde el SQL Editor de Supabase.
5. Inicia Uvicorn desde la raíz del proyecto con el módulo del paquete: `python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`. También puedes usar `python -m backend.main`.
6. Abre `http://127.0.0.1:8000` para usar la interfaz y `http://127.0.0.1:8000/docs` para consultar la documentación local de la API.

La secret key debe permanecer solo en el backend. No la incluyas en HTML, CSS ni JavaScript del navegador.

## Estructura del proyecto

- `backend/`: API FastAPI, importador de Excel y dependencias Python.
- `frontend/`: página HTML, estilos CSS y JavaScript del CRM.
- `adjuntos/`: imágenes y recursos adjuntos.
- `migrations/` y `scripts/`: migraciones de Supabase y utilidades SQL.
- Raíz: `render.yaml`, README, configuración de entorno y versión de Python.

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
- `GET /api/gestiones/promesas-hoy`: lista las cuentas con promesa de pago para la fecha local actual.
- `GET /api/reportes/gestiones.xlsx`: descarga un Excel filtrable por fecha y resultado.
- `GET /api/carteras/{fk_cartera}/gestiones`: devuelve el historial paginado de una cuenta.
- `POST /api/gestiones`: registra una llamada y su resultado para una cuenta.
- `POST /api/gestiones/importar`: importa el historial desde la pestaña `Gestiones` de un libro manual.
- `POST /api/carteras/{fk_cartera}/referencias`: agrega la tercera referencia de una cuenta.
- `POST /api/carteras/importar`: valida el layout, agrega cuentas nuevas y omite claves ya existentes.

## Importación de la cartera

El importador usa pandas para leer Excel y CSV, busca encabezados en las primeras 30 filas y conecta las columnas con sus campos de Supabase por nombre normalizado, aunque cambie su orden. Convierte los valores detectados por pandas a texto y después los normaliza al tipo esperado por Supabase (fecha, número entero o decimal, o texto), para evitar enviar valores incompatibles. Elimina espacios internos y externos de `IdCuenta` y `No. de Crédito` antes de importar. Los encabezados repetidos de referencias, frecuencia y estatus de correo se asignan por orden de aparición. FINORE identifica cada cuenta con `IdCuenta`; BORDER CREDIT usa su `No. de Crédito`. Se conservan en columnas distintas y cada una tiene una clave de importación adecuada. Acepta `.xlsx`, `.xls`, `.xlsm` y `.csv`, con un máximo de 25 MB y 100,000 cuentas por archivo. La migración 003 registra BORDER CREDIT y FINORE para que aparezcan en el selector.

`Clave Cliente` se guarda en `carteras.id_cuenta` y `No. de Crédito` en `carteras.numero_credito`; ambos permanecen como identificadores distintos. El selector asigna la financiera y, opcionalmente, un agente. El agente que venga en el libro se conserva en `agente_texto`.

La carga inserta en lotes usando el índice único `fk_financiera + clave_importacion`. Si una cuenta ya existe para esa financiera, Supabase la omite y conserva los datos guardados. La respuesta informa cuántas cuentas nuevas agregó y cuántas omitió. Las cuentas nuevas envían los campos mapeados del layout; las celdas vacías se guardan como `NULL`. El inicio muestra el total de cuentas y el conteo separado de BORDER CREDIT y FINORE.

La vista “Cargar gestiones” importa todas las filas válidas de la pestaña `Gestiones` de FINORE o BORDER CREDIT y las relaciona con `id_cuenta` o `numero_credito` de la financiera elegida. Omite filas sin resultado, fecha o cuenta correspondiente; los resultados se normalizan al catálogo de 22 estatus del CRM. Las cargas idénticas se reconocen mediante `import_key` y no duplican registros. Requiere la migración 011.

La búsqueda utiliza la función SQL `buscar_carteras` para consultar coincidencias en la base de datos y entrega páginas de resultados. En nombres, busca cada palabra introducida, así que permite buscar por uno o varios nombres o apellidos sin importar que solo se escriba una parte.

El resumen de inicio utiliza `resumen_dashboard_general` para calcular las métricas directamente en Supabase. También muestra las promesas con vencimiento hoy, agrupadas por cuenta, con importe y acceso directo para seleccionarla; la actividad de hoy aparece junto a esa lista. La sección “Mi cartera” muestra temporalmente la cartera general y pagina las cuentas; se podrá filtrar por agente cuando haya cuentas individuales.

La vista “Registrar gestión” permite buscar una cuenta, seleccionar a quién se llamó, guardar uno de los 22 estatus y el comentario, filtrar el historial y consultar su detalle. También permite agregar una tercera referencia a la cuenta. “05.-Promesa de Pago” solicita fecha y monto. Mientras no exista login por agente, las gestiones se guardan con `fk_agente = NULL`; las migraciones 005 y 009 habilitan ese flujo y almacenan la persona contactada. El inicio muestra gestiones de hoy, actualiza métricas cada minuto y combina resultados de seguimiento. La vista “Reportes” descarga gestiones filtradas por fecha y resultado en Excel.

Las métricas de gestión usan los nuevos resultados `05.-Promesa de Pago`, `20.-Negativa` y `09`–`11` para mensajes; las gestiones telefónicas cuentan según `tipo_contacto`. La migración 011 actualiza los cálculos del dashboard y de seguimientos pendientes.

## Integración con NBX/VICIdial

El CRM acepta `?credito=NUMERO` en su URL. Tras iniciar sesión, busca ese número de crédito directamente en Supabase y abre la cuenta si hay una sola coincidencia. Si aparece en más de una financiera, muestra las opciones para elegir.

En la campaña de VICIdial (por ejemplo, la 005), configura el campo Web Form con una URL como:

```text
VARhttps://mb-consultoria.onrender.com/?credito=--A--first_name--B--
```

Este ejemplo supone que el número de crédito está guardado en el campo **First** de VICIdial, cuyo marcador es `first_name`. Configura el Web Form para abrir en una pestaña o ventana principal si esa opción está disponible; así el CRM conserva su sesión de inicio. La documentación de VICIdial describe el prefijo `VAR` y los marcadores `--A--campo--B--`.

## Despliegue en Render

El archivo `render.yaml` permanece en la raíz y configura un solo servicio web que sirve la página y la API bajo el mismo dominio. Render instala `requirements.txt` desde la raíz y ejecuta `backend.main:app` en el puerto que proporciona mediante `PORT`. Deja **Root Directory** vacío en Render para que los comandos y las carpetas `backend/`, `frontend/` y `adjuntos/` estén disponibles desde la raíz del repositorio.

1. En Render, crea un Blueprint desde el repositorio y selecciona `render.yaml`.
2. Cuando Render lo solicite, agrega `SUPABASE_URL` y `SUPABASE_SECRET_KEY` como variables secretas.
3. Define `CRM_ACCESS_PASSWORD` como una contraseña aleatoria de al menos 32 caracteres. Guárdala en un administrador de contraseñas y compártela solo con el equipo.
4. Render genera `SESSION_SECRET` automáticamente. No cambies ni publiques ese valor.
5. Completa la creación del servicio y abre su URL. La pantalla de acceso pedirá la contraseña del despacho.

En producción la API exige la sesión; la cookie es `HttpOnly`, segura y vence después de ocho horas. El servicio falla al iniciar si faltan la contraseña o el secreto de sesión. El acceso local sigue abierto si no defines `CRM_ACCESS_PASSWORD` en `.env`.

Esta contraseña es compartida y todavía no identifica agentes ni asigna permisos por usuario. Úsala para pruebas del despacho; antes de operar con cuentas individuales, habrá que integrar autenticación por agente y limitar el acceso a la cartera asignada. `SUPABASE_SECRET_KEY` permanece solamente en el backend y debe configurarse en el entorno de Render, nunca en el navegador ni en Git.

## Limpiar datos de prueba

El script `scripts/limpiar_datos_prueba.sql` elimina registros de `pagos`, `gestiones` y `carteras` en una transacción. Conserva los catálogos de `financieras` y `agentes`. No forma parte de las migraciones; ejecútalo manualmente en el SQL Editor de Supabase solo cuando quieras vaciar esos datos.
