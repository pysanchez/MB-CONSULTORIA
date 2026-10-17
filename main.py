from datetime import datetime, time, timedelta
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
import hashlib
import hmac
import os
import time as system_time

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from supabase import Client, create_client

from excel_import import ImportFormatError, parse_cartera_file


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
LOCAL_TIMEZONE = ZoneInfo("America/Mexico_City")
IS_PRODUCTION = os.getenv("RENDER", "").lower() == "true" or (
    os.getenv("ENVIRONMENT", "").lower() == "production"
)
CRM_ACCESS_PASSWORD = os.getenv("CRM_ACCESS_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_COOKIE_NAME = "mb_crm_session"
SESSION_MAX_AGE = 8 * 60 * 60
AUTH_ENABLED = IS_PRODUCTION or bool(CRM_ACCESS_PASSWORD)

if IS_PRODUCTION:
    if not CRM_ACCESS_PASSWORD or len(CRM_ACCESS_PASSWORD) < 32:
        raise RuntimeError(
            "En producción configura CRM_ACCESS_PASSWORD con al menos 32 caracteres."
        )
    if len(SESSION_SECRET) < 32:
        raise RuntimeError(
            "En producción configura SESSION_SECRET con al menos 32 caracteres."
        )
elif AUTH_ENABLED and len(SESSION_SECRET) < 32:
    raise RuntimeError(
        "Si configuras CRM_ACCESS_PASSWORD en local, SESSION_SECRET debe tener al menos 32 caracteres."
    )


class GestionCreate(BaseModel):
    fk_cartera: int = Field(gt=0)
    estatus_contacto: Literal["titular", "tercero", "sin_contacto"]
    codigo_resultado: Literal[
        "promesa",
        "negativa",
        "recado",
        "pago_reportado",
        "sin_acuerdo",
        "no_contesto",
        "numero_incorrecto",
    ]
    comentario: str | None = Field(default=None, max_length=5000)
    fecha_promesa: date | None = None
    monto_promesa: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )


class LoginRequest(BaseModel):
    password: str = Field(default="", max_length=256)

app = FastAPI(
    title="MB CONSULTORIA CRM API",
    description="API de gestión para MB CONSULTORIA.",
    version="0.4.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

allowed_origins = []
if not IS_PRODUCTION:
    allowed_origins.extend([
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ])

def create_session_token() -> str:
    issued_at = str(int(system_time.time()))
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        issued_at.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{issued_at}.{signature}"


def is_valid_session(token: str | None) -> bool:
    if not AUTH_ENABLED:
        return True
    if not token:
        return False

    try:
        issued_at_text, provided_signature = token.split(".", maxsplit=1)
        issued_at = int(issued_at_text)
    except (ValueError, TypeError):
        return False

    age = int(system_time.time()) - issued_at
    if age < 0 or age > SESSION_MAX_AGE:
        return False

    expected_signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        issued_at_text.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided_signature, expected_signature)


@app.middleware("http")
async def protect_api(request: Request, call_next):
    path = request.url.path
    public_api_paths = {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/health",
    }

    if AUTH_ENABLED and path.startswith("/api/") and path not in public_api_paths:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not is_valid_session(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Inicia sesión para usar el CRM."},
            )

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Configura SUPABASE_URL y SUPABASE_SECRET_KEY en el entorno del servicio o en .env local.",
        )

    try:
        return create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo inicializar el cliente de Supabase.",
        ) from exc


@app.get("/", include_in_schema=False)
def serve_homepage() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


@app.get("/style.css", include_in_schema=False)
def serve_stylesheet() -> FileResponse:
    return FileResponse(BASE_DIR / "style.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
def serve_frontend_script() -> FileResponse:
    return FileResponse(BASE_DIR / "app.js", media_type="text/javascript")


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response) -> dict[str, bool]:
    if not AUTH_ENABLED:
        return {"authenticated": True, "auth_required": False}

    if not hmac.compare_digest(
        payload.password.encode("utf-8"),
        CRM_ACCESS_PASSWORD.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="La contraseña no es correcta.")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="strict",
        path="/",
    )
    return {"authenticated": True, "auth_required": True}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="strict",
        path="/",
    )
    return {"authenticated": False}


def count_rows(query) -> int:
    response = query.execute()
    return response.count or 0


def count_gestiones(
    supabase: Client,
    fk_agente: int,
    tipo_contacto: str | None = None,
    fecha_inicio: datetime | None = None,
    fecha_fin: datetime | None = None,
    resultado: str | None = None,
) -> int:
    query = supabase.table("gestiones").select("*", count="exact", head=True)
    query = query.eq("fk_agente", fk_agente)

    if tipo_contacto:
        query = query.ilike("tipo_contacto", f"%{tipo_contacto}%")
    if fecha_inicio:
        query = query.gte("fecha_gestion", fecha_inicio.isoformat())
    if fecha_fin:
        query = query.lt("fecha_gestion", fecha_fin.isoformat())
    if resultado:
        query = query.or_(
            f"estatus_contacto.ilike.%{resultado}%,"
            f"codigo_resultado.ilike.%{resultado}%"
        )

    response = query.execute()
    return response.count or 0


@app.get("/api/health")
def health_check() -> dict[str, str]:
    supabase = get_supabase()

    try:
        supabase.table("financieras").select("id_financiera").limit(1).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="La API inició, pero no pudo consultar Supabase. Revisa URL, key y esquema.",
        ) from exc

    return {"api": "ok", "supabase": "connected"}


@app.get("/api/financieras")
def list_financieras() -> list[dict[str, object]]:
    supabase = get_supabase()

    try:
        response = (
            supabase.table("financieras")
            .select("id_financiera,nombre_financiera")
            .order("nombre_financiera")
            .execute()
        )
        allowed_financials = {"BORDER CREDIT", "FINORE"}
        return [
            financial
            for financial in response.data or []
            if financial["nombre_financiera"].strip().upper() in allowed_financials
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron consultar las financieras.",
        ) from exc


@app.get("/api/agentes")
def list_agentes() -> list[dict[str, object]]:
    supabase = get_supabase()

    try:
        response = (
            supabase.table("agentes")
            .select(
                "id_agente,nombre_agente,numero_agente,horario_agente,"
                "tiempo_conexion_minutos,llamadas_realizadas,contactos_titular,"
                "llamadas_no_contestadas,monto_promesado,monto_recuperado,"
                "gestiones_totales,ultima_fecha_conexion"
            )
            .order("nombre_agente")
            .execute()
        )
        return response.data or []
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron consultar los agentes.",
        ) from exc


@app.get("/api/carteras")
def list_carteras(
    buscar: str | None = Query(default=None, description="Crédito, teléfono o nombre del cliente"),
    fk_agente: int | None = Query(default=None, ge=1),
    fk_financiera: int | None = Query(default=None, ge=1),
    limite: int = Query(default=50, ge=1, le=100),
    desde: int = Query(default=0, ge=0),
) -> dict[str, object]:
    supabase = get_supabase()
    search_term = (buscar or "").strip()

    try:
        if search_term:
            response = supabase.rpc(
                "buscar_carteras",
                {
                    "p_buscar": search_term,
                    "p_fk_agente": fk_agente,
                    "p_fk_financiera": fk_financiera,
                    "p_limite": limite + 1,
                    "p_desde": desde,
                },
            ).execute()
            accounts = response.data or []
            has_more = len(accounts) > limite
            accounts = accounts[:limite]
        else:
            query = supabase.table("carteras").select("*")
            if fk_agente is not None:
                query = query.eq("fk_agente", fk_agente)
            if fk_financiera is not None:
                query = query.eq("fk_financiera", fk_financiera)
            response = (
                query.order("id_cartera")
                .range(desde, desde + limite)
                .execute()
            )
            accounts = response.data or []
            has_more = len(accounts) > limite
            accounts = accounts[:limite]

        agent_ids = list({account["fk_agente"] for account in accounts if account.get("fk_agente")})
        finance_ids = list({account["fk_financiera"] for account in accounts if account.get("fk_financiera")})

        agents = []
        if agent_ids:
            agents = (
                supabase.table("agentes")
                .select("id_agente,nombre_agente")
                .in_("id_agente", agent_ids)
                .execute()
                .data
                or []
            )

        finances = []
        if finance_ids:
            finances = (
                supabase.table("financieras")
                .select("id_financiera,nombre_financiera")
                .in_("id_financiera", finance_ids)
                .execute()
                .data
                or []
            )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron consultar las carteras. Revisa las tablas y políticas de Supabase.",
        ) from exc

    agents_by_id = {agent["id_agente"]: agent for agent in agents}
    finances_by_id = {finance["id_financiera"]: finance for finance in finances}
    items = [
        {
            **account,
            "agente": agents_by_id.get(account.get("fk_agente")),
            "financiera": finances_by_id.get(account.get("fk_financiera")),
        }
        for account in accounts
    ]

    return {
        "items": items,
        "hay_mas": has_more,
        "limite": limite,
        "desde": desde,
        "buscar": buscar,
        "fk_agente": fk_agente,
        "fk_financiera": fk_financiera,
    }


@app.get("/api/carteras/{fk_cartera}/gestiones")
def list_account_gestiones(
    fk_cartera: int,
    limite: int = Query(default=20, ge=1, le=100),
    desde: int = Query(default=0, ge=0),
) -> dict[str, object]:
    supabase = get_supabase()

    try:
        response = (
            supabase.table("gestiones")
            .select(
                "id_gestion,fk_cartera,fecha_gestion,tipo_contacto,estatus_contacto,"
                "codigo_resultado,comentario,fecha_promesa,monto_promesa"
            )
            .eq("fk_cartera", fk_cartera)
            .order("fecha_gestion", desc=True)
            .range(desde, desde + limite)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudo consultar el historial de gestiones.",
        ) from exc

    items = response.data or []
    has_more = len(items) > limite
    return {
        "items": items[:limite],
        "hay_mas": has_more,
        "limite": limite,
        "desde": desde,
    }


@app.post("/api/gestiones", status_code=201)
def create_gestion(gestion: GestionCreate) -> dict[str, object]:
    supabase = get_supabase()

    if gestion.codigo_resultado == "promesa":
        if gestion.fecha_promesa is None or gestion.monto_promesa is None:
            raise HTTPException(
                status_code=422,
                detail="Una promesa requiere fecha y monto prometido.",
            )
    else:
        gestion.fecha_promesa = None
        gestion.monto_promesa = None

    try:
        account_response = (
            supabase.table("carteras")
            .select("id_cartera")
            .eq("id_cartera", gestion.fk_cartera)
            .limit(1)
            .execute()
        )
        if not account_response.data:
            raise HTTPException(status_code=404, detail="La cuenta seleccionada no existe.")

        record = gestion.model_dump(mode="json")
        record["tipo_contacto"] = "llamada"
        record["fk_agente"] = None
        record["fecha_gestion"] = datetime.now(LOCAL_TIMEZONE).replace(
            tzinfo=None,
        ).isoformat(sep=" ")
        response = (
            supabase.table("gestiones")
            .insert(record)
            .select(
                "id_gestion,fk_cartera,fecha_gestion,tipo_contacto,estatus_contacto,"
                "codigo_resultado,comentario,fecha_promesa,monto_promesa"
            )
            .single()
            .execute()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No se pudo guardar la gestión. Confirma que aplicaste la migración 005 "
                "para permitir gestiones sin agente asignado."
            ),
        ) from exc

    return {"mensaje": "La gestión se registró correctamente.", "gestion": response.data}


@app.get("/api/dashboard/general")
def get_general_dashboard() -> dict[str, object]:
    supabase = get_supabase()
    now = datetime.now(LOCAL_TIMEZONE)
    yesterday = now.date() - timedelta(days=1)
    start_of_yesterday = datetime.combine(yesterday, time.min)
    start_of_today = datetime.combine(now.date(), time.min)

    try:
        response = supabase.rpc(
            "resumen_dashboard_general",
            {
                "p_inicio_ayer": start_of_yesterday.isoformat(sep=" "),
                "p_inicio_hoy": start_of_today.isoformat(sep=" "),
            },
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No se pudo consultar el resumen general. "
                "Confirma que aplicaste la migración 004 en Supabase."
            ),
        ) from exc

    summary = response.data or {}
    if isinstance(summary, list):
        summary = summary[0] if summary else {}

    return {"alcance": "general", **summary}


@app.get("/api/dashboard/{fk_agente}")
def get_dashboard(fk_agente: int) -> dict[str, object]:
    supabase = get_supabase()
    now = datetime.now(LOCAL_TIMEZONE)
    today = now.date()
    yesterday = today - timedelta(days=1)
    start_of_yesterday = datetime.combine(yesterday, time.min)
    start_of_today = datetime.combine(today, time.min)

    try:
        assigned_accounts = count_rows(
            supabase.table("carteras")
            .select("*", count="exact", head=True)
            .eq("fk_agente", fk_agente)
        )
        calls_yesterday = count_gestiones(
            supabase,
            fk_agente,
            tipo_contacto="llamada",
            fecha_inicio=start_of_yesterday,
            fecha_fin=start_of_today,
        )
        calls_total = count_gestiones(
            supabase,
            fk_agente,
            tipo_contacto="llamada",
        )
        promises = count_gestiones(supabase, fk_agente, resultado="promesa")
        refusals = count_gestiones(supabase, fk_agente, resultado="negativa")
        messages = count_gestiones(supabase, fk_agente, resultado="recado")
        payments = count_rows(
            supabase.table("pagos")
            .select("*", count="exact", head=True)
            .eq("fk_agente", fk_agente)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudo construir el resumen. Revisa las tablas y políticas de Supabase.",
        ) from exc

    return {
        "fk_agente": fk_agente,
        "cuentas_gestionadas": assigned_accounts,
        "llamadas_ayer": calls_yesterday,
        "llamadas_acumuladas": calls_total,
        "cuentas_promesadas": promises,
        "negativas_de_pago": refusals,
        "cuentas_con_recado": messages,
        "pagos_reportados": payments,
    }


@app.post("/api/carteras/importar")
async def import_cartera(
    fk_financiera: int = Form(..., ge=1),
    file: UploadFile = File(...),
) -> dict[str, object]:
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls", ".xlsm", ".csv")):
        raise HTTPException(
            status_code=415,
            detail="Formato no admitido. Usa .xlsx, .xls, .xlsm o .csv.",
        )

    contents = await file.read(25 * 1024 * 1024 + 1)
    await file.close()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="El archivo supera el límite de 25 MB.",
        )

    try:
        records = parse_cartera_file(contents, filename)
    except ImportFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="No se pudo leer el archivo. Verifica que no esté dañado o protegido con contraseña.",
        ) from exc

    supabase = get_supabase()

    try:
        finance_response = (
            supabase.table("financieras")
            .select("id_financiera,nombre_financiera")
            .eq("id_financiera", fk_financiera)
            .limit(1)
            .execute()
        )
        if not finance_response.data:
            raise HTTPException(status_code=404, detail="La financiera seleccionada no existe.")

        for record in records:
            record["fk_financiera"] = fk_financiera

        processed = 0
        batch_size = 500
        for start in range(0, len(records), batch_size):
            batch = records[start:start + batch_size]
            try:
                supabase.table("carteras").upsert(
                    batch,
                    on_conflict="fk_financiera,numero_credito",
                ).execute()
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"La importación se detuvo después de {processed} filas. "
                        "Confirma que aplicaste la migración SQL; puedes volver a cargar "
                        "el mismo archivo después de corregir el problema."
                    ),
                ) from exc
            processed += len(batch)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Supabase rechazó la carga. Revisa la migración SQL y las políticas de acceso.",
        ) from exc

    return {
        "mensaje": "La cartera se importó correctamente.",
        "registros_procesados": processed,
        "fk_financiera": fk_financiera,
        "nombre_financiera": finance_response.data[0]["nombre_financiera"],
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)





