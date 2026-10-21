from datetime import datetime, time, timedelta
from datetime import date
from decimal import Decimal
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
import hashlib
import hmac
import logging
import os
import time as system_time

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client, create_client
import pandas as pd

from excel_import import ImportFormatError, parse_cartera_file


logger = logging.getLogger(__name__)

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
    persona_contactada: str = Field(min_length=1, max_length=200)
    telefono_contactado: str | None = Field(default=None, max_length=30)
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


class ReferenciaCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    telefono: str = Field(min_length=7, max_length=30)
    parentesco: str | None = Field(default=None, max_length=80)
    domicilio: str | None = Field(default=None, max_length=500)

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


@app.get("/mbconsultoria.jpeg", include_in_schema=False)
def serve_login_logo() -> FileResponse:
    return FileResponse(BASE_DIR / "mbconsultoria.jpeg", media_type="image/jpeg")


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


@app.get("/api/carteras/por-numero-credito")
def get_carteras_by_credit(
    numero_credito: str = Query(..., min_length=1, max_length=100),
) -> dict[str, list[dict[str, object]]]:
    credit_number = numero_credito.strip()
    if not credit_number:
        raise HTTPException(
            status_code=422,
            detail="El número de crédito es obligatorio.",
        )

    supabase = get_supabase()
    try:
        accounts = (
            supabase.table("carteras")
            .select("*")
            .eq("numero_credito", credit_number)
            .order("id_cartera")
            .limit(10)
            .execute()
            .data
            or []
        )
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
            detail="No se pudo buscar el número de crédito en Supabase.",
        ) from exc

    agents_by_id = {agent["id_agente"]: agent for agent in agents}
    finances_by_id = {finance["id_financiera"]: finance for finance in finances}
    return {
        "items": [
            {
                **account,
                "agente": agents_by_id.get(account.get("fk_agente")),
                "financiera": finances_by_id.get(account.get("fk_financiera")),
            }
            for account in accounts
        ],
    }


@app.get("/api/carteras/{fk_cartera}/gestiones")
def list_account_gestiones(
    fk_cartera: int,
    limite: int = Query(default=20, ge=1, le=100),
    desde: int = Query(default=0, ge=0),
    codigo_resultado: str | None = Query(default=None, max_length=50),
) -> dict[str, object]:
    supabase = get_supabase()

    try:
        query = (
            supabase.table("gestiones")
            .select(
                "id_gestion,fk_cartera,fecha_gestion,tipo_contacto,estatus_contacto,"
                "codigo_resultado,persona_contactada,telefono_contactado,"
                "comentario,fecha_promesa,monto_promesa"
            )
            .eq("fk_cartera", fk_cartera)
        )
        if codigo_resultado:
            query = query.eq("codigo_resultado", codigo_resultado)
        response = query.order("fecha_gestion", desc=True).range(
            desde,
            desde + limite,
        ).execute()
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
                "codigo_resultado,persona_contactada,telefono_contactado,"
                "comentario,fecha_promesa,monto_promesa"
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
                "No se pudo guardar la gestión. Confirma que aplicaste las migraciones "
                "005 y 009 en Supabase."
            ),
        ) from exc

    return {"mensaje": "La gestión se registró correctamente.", "gestion": response.data}


@app.post("/api/carteras/{fk_cartera}/referencias", status_code=201)
def create_account_reference(
    fk_cartera: int,
    referencia: ReferenciaCreate,
) -> dict[str, object]:
    supabase = get_supabase()

    try:
        account_response = (
            supabase.table("carteras")
            .select("id_cartera,ref3_nombre,ref3_tel")
            .eq("id_cartera", fk_cartera)
            .limit(1)
            .execute()
        )
        if not account_response.data:
            raise HTTPException(status_code=404, detail="La cuenta seleccionada no existe.")

        account = account_response.data[0]
        if account.get("ref3_nombre") or account.get("ref3_tel"):
            raise HTTPException(
                status_code=409,
                detail="La cuenta ya tiene una tercera referencia registrada.",
            )

        updated = (
            supabase.table("carteras")
            .update({
                "ref3_nombre": referencia.nombre.strip(),
                "ref3_tel": referencia.telefono.strip(),
                "ref3_parentesco": referencia.parentesco,
                "ref3_domicilio": referencia.domicilio,
            })
            .eq("id_cartera", fk_cartera)
            .select("id_cartera,ref3_nombre,ref3_tel,ref3_parentesco,ref3_domicilio")
            .single()
            .execute()
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudo guardar la referencia. Confirma que aplicaste la migración 009.",
        ) from exc

    return {"mensaje": "La referencia se registró correctamente.", "referencia": updated.data}


@app.get("/api/dashboard/general")
def get_general_dashboard() -> dict[str, object]:
    supabase = get_supabase()
    now = datetime.now(LOCAL_TIMEZONE)
    yesterday = now.date() - timedelta(days=1)
    start_of_yesterday = datetime.combine(yesterday, time.min)
    start_of_today = datetime.combine(now.date(), time.min)
    start_of_tomorrow = start_of_today + timedelta(days=1)

    try:
        response = supabase.rpc(
            "resumen_dashboard_general",
            {
                "p_inicio_ayer": start_of_yesterday.isoformat(sep=" "),
                "p_inicio_hoy": start_of_today.isoformat(sep=" "),
            },
        ).execute()
        today_count = (
            supabase.table("gestiones")
            .select("id_gestion", count="exact", head=True)
            .gte("fecha_gestion", start_of_today.isoformat(sep=" "))
            .lt("fecha_gestion", start_of_tomorrow.isoformat(sep=" "))
            .execute()
        ).count or 0
        pending_count = supabase.rpc("resumen_seguimientos_pendientes").execute().data or 0
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No se pudo consultar el resumen general. "
                "Confirma que aplicaste las migraciones 004 y 010 en Supabase."
            ),
        ) from exc

    summary = response.data or {}
    if isinstance(summary, list):
        summary = summary[0] if summary else {}

    try:
        financials_response = (
            supabase.table("financieras")
            .select("id_financiera,nombre_financiera")
            .execute()
        )
        portfolio_counts: dict[str, int] = {}
        for financial in financials_response.data or []:
            count_response = (
                supabase.table("carteras")
                .select("id_cartera", count="exact", head=True)
                .eq("fk_financiera", financial["id_financiera"])
                .execute()
            )
            portfolio_counts[financial["nombre_financiera"].strip().upper()] = (
                count_response.count or 0
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron consultar las cuentas por financiera.",
        ) from exc

    return {
        "alcance": "general",
        **summary,
        "cuentas_por_financiera": portfolio_counts,
        "gestiones_hoy": today_count,
        "gestiones_pendientes": pending_count,
    }


@app.get("/api/gestiones/hoy")
def list_today_gestiones(
    limite: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    supabase = get_supabase()
    now = datetime.now(LOCAL_TIMEZONE)
    start_of_day = datetime.combine(now.date(), time.min)
    start_of_tomorrow = start_of_day + timedelta(days=1)

    try:
        response = (
            supabase.table("gestiones")
            .select(
                "id_gestion,fk_cartera,fecha_gestion,codigo_resultado,"
                "persona_contactada,telefono_contactado,comentario"
            )
            .gte("fecha_gestion", start_of_day.isoformat(sep=" "))
            .lt("fecha_gestion", start_of_tomorrow.isoformat(sep=" "))
            .order("fecha_gestion", desc=True)
            .range(0, limite - 1)
            .execute()
        )
        count_response = (
            supabase.table("gestiones")
            .select("fk_cartera", count="exact")
            .gte("fecha_gestion", start_of_day.isoformat(sep=" "))
            .lt("fecha_gestion", start_of_tomorrow.isoformat(sep=" "))
            .range(0, 999)
            .execute()
        )
        count_rows = count_response.data or []
        total_rows = count_response.count or len(count_rows)
        offset = len(count_rows)

        while offset < total_rows:
            page = (
                supabase.table("gestiones")
                .select("fk_cartera")
                .gte("fecha_gestion", start_of_day.isoformat(sep=" "))
                .lt("fecha_gestion", start_of_tomorrow.isoformat(sep=" "))
                .range(offset, offset + 999)
                .execute()
            )
            page_rows = page.data or []
            if not page_rows:
                break
            count_rows.extend(page_rows)
            offset += len(page_rows)

        counts_by_account: dict[str, int] = {}
        for row in count_rows:
            account_key = str(row["fk_cartera"])
            counts_by_account[account_key] = counts_by_account.get(account_key, 0) + 1

        management_items = response.data or []
        account_ids = list({item["fk_cartera"] for item in management_items})
        accounts = []
        if account_ids:
            accounts = (
                supabase.table("carteras")
                .select("id_cartera,cliente,numero_credito")
                .in_("id_cartera", account_ids)
                .execute()
                .data
                or []
            )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron consultar las gestiones de hoy. Confirma la migración 009.",
        ) from exc

    accounts_by_id = {account["id_cartera"]: account for account in accounts}
    return {
        "fecha": now.date().isoformat(),
        "conteos_por_cuenta": counts_by_account,
        "items": [
            {**item, "cuenta": accounts_by_id.get(item["fk_cartera"])}
            for item in management_items
        ],
    }


@app.get("/api/reportes/gestiones.xlsx")
def export_gestiones_xlsx(
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    codigo_resultado: str | None = Query(default=None, max_length=50),
) -> StreamingResponse:
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=422,
            detail="La fecha inicial no puede ser posterior a la final.",
        )

    supabase = get_supabase()
    fields = (
        "id_gestion,fk_cartera,fecha_gestion,tipo_contacto,estatus_contacto,"
        "persona_contactada,telefono_contactado,codigo_resultado,comentario,"
        "fecha_promesa,monto_promesa"
    )
    management_items = []
    page_size = 1000

    try:
        for page_start in range(0, 50000, page_size):
            query = supabase.table("gestiones").select(fields)
            if fecha_inicio:
                query = query.gte(
                    "fecha_gestion",
                    datetime.combine(fecha_inicio, time.min).isoformat(sep=" "),
                )
            if fecha_fin:
                query = query.lt(
                    "fecha_gestion",
                    datetime.combine(fecha_fin + timedelta(days=1), time.min).isoformat(sep=" "),
                )
            if codigo_resultado:
                query = query.eq("codigo_resultado", codigo_resultado)
            batch = (
                query.order("fecha_gestion")
                .range(page_start, page_start + page_size - 1)
                .execute()
                .data
                or []
            )
            management_items.extend(batch)
            if len(batch) < page_size:
                break

        if len(management_items) >= 50000:
            raise HTTPException(
                status_code=413,
                detail="El reporte supera 50,000 gestiones. Limita el rango de fechas.",
            )

        account_ids = list({item["fk_cartera"] for item in management_items})
        accounts_by_id = {}
        for start in range(0, len(account_ids), 500):
            account_batch = (
                supabase.table("carteras")
                .select("id_cartera,cliente,numero_credito,fk_financiera")
                .in_("id_cartera", account_ids[start:start + 500])
                .execute()
                .data
                or []
            )
            accounts_by_id.update({item["id_cartera"]: item for item in account_batch})

        financial_ids = list({item["fk_financiera"] for item in accounts_by_id.values()})
        financials = (
            supabase.table("financieras")
            .select("id_financiera,nombre_financiera")
            .in_("id_financiera", financial_ids)
            .execute()
            .data
            if financial_ids
            else []
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="No se pudo generar el reporte.") from exc

    financials_by_id = {
        item["id_financiera"]: item["nombre_financiera"]
        for item in financials
    }
    rows = []
    for management in management_items:
        account = accounts_by_id.get(management["fk_cartera"], {})
        rows.append({
            "Fecha y hora": management.get("fecha_gestion"),
            "Cliente": account.get("cliente"),
            "Número de crédito": account.get("numero_credito"),
            "Financiera": financials_by_id.get(account.get("fk_financiera")),
            "Persona contactada": management.get("persona_contactada"),
            "Teléfono contactado": management.get("telefono_contactado"),
            "Resultado": management.get("codigo_resultado"),
            "Tipo de contacto": management.get("estatus_contacto"),
            "Comentario": management.get("comentario"),
            "Fecha promesa": management.get("fecha_promesa"),
            "Monto promesa": management.get("monto_promesa"),
        })

    workbook = BytesIO()
    pd.DataFrame(rows).to_excel(workbook, index=False, engine="openpyxl")
    workbook.seek(0)
    return StreamingResponse(
        workbook,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="reporte_gestiones.xlsx"'},
    )


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
        inserted = 0
        batch_size = 500
        for start in range(0, len(records), batch_size):
            batch = records[start:start + batch_size]
            try:
                batch_response = supabase.table("carteras").upsert(
                    batch,
                    on_conflict="fk_financiera,clave_importacion",
                    ignore_duplicates=True,
                ).execute()
                inserted += len(batch_response.data or [])
            except Exception as exc:
                logger.exception(
                    "Supabase rejected a cartera batch after %s processed rows",
                    processed,
                )
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

    omitted = len(records) - inserted
    message = (
        "La importacion se completo."
        if inserted
        else "No se agregaron cuentas nuevas; todas ya existian."
    )
    return {
        "mensaje": message,
        "registros_procesados": inserted,
        "registros_omitidos": omitted,
        "fk_financiera": fk_financiera,
        "nombre_financiera": finance_response.data[0]["nombre_financiera"],
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)





