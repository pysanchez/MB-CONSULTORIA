from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO, StringIO
from pathlib import Path
import re
import unicodedata
import logging

import pandas as pd


logger = logging.getLogger(__name__)


FIELD_HEADERS = {
    "id_cuenta": ("clave cliente", "clave", "id cuenta", "idcuenta"),
    "numero_credito": ("no de credito", "numero de credito", "no credito"),
    "estatus_promesa_act": ("estatus promesa act", "estatus promesa actual", "esta pp actual"),
    "estatus_promesa_ant": ("estatus promesa ant", "estatus promesa anterior", "est pp ant"),
    "asignacion": ("gestionada", "asignacion"), "agente_texto": ("agente",),
    "gestiones": ("gestiones",), "campanas": ("campanas",), "prioridad": ("prioridad",),
    "campana": ("campana", "campanas mb", "campana mb"), "cartera_campa": ("cartera campa",),
    "cartera": ("cartera",), "convenio": ("convenio",),
    "cliente": ("nombre cliente", "cliente", "nombre completo"),
    "estatus": ("estatus",), "ult_gestion": ("ult gestion", "ultima gestion"),
    "frecuencia": ("frecuencia",), "frecuencia_detalle": ("frecuencia",),
    "comentario": ("comentario",),
    "excel_pagos": ("pagos",), "rec_mb": ("rec mb",),
    "fecha_asig": ("fecha asig", "fecha asignacion"),
    "fecha_arranque": ("fch arranque", "fecha arranque"),
    "fecha_prom": ("fecha prom", "fecha promesa"), "monto_prom": ("monto prom", "monto promesa"),
    "proyeccion_cierre": ("proyeccion cierre",),
    "sdo_vencido_inicial": ("sdo vencido inicial", "saldo vencido inicial"),
    "saldo_vencido_actual": ("sdo vencido actual", "saldo vencido actual"),
    "pagos_sep": ("pagos sep",), "pagos_ago": ("pagos ago",), "pagos_jul": ("pagos jul",),
    "empresa_pagadora": ("empresa pagadora",),
    "telempresa": ("telempresa", "telefono empresa"),
    "telempresa_alterno": ("tel empresa alterno", "telefono empresa alterno"),
    "correo_empresa": ("correo empresa", "email empresa"),
    "correo_empresa_alterno": ("correo empresa alterno", "email empresa alterno"),
    "estatus_correo_empresa": ("estatus correo 1", "estatus correo empresa", "estatus correo"),
    "estatus_correo_empresa_2": ("estatus correo 2",),
    "referencia_1": ("referencia 1", "ref 1"), "ref1_tel": ("tel ref1", "tel ref 1", "telefono ref1"),
    "ref1_nombre": ("ref1", "nombre relacion", "nombre referencia 1"),
    "ref1_tipo_telefono": ("tipo telefono", "tipo telefono referencia 1"),
    "ref1_parentesco": ("parentesco", "parentesco referencia 1", "parentezco"),
    "referencia_2": ("referencia 2", "ref 2"), "ref2_tel": ("tel ref2", "tel ref 2", "telefono ref2"),
    "en_predic": ("en predic", "en prediccion"),
    "ref2_nombre": ("ref2", "nombre relacion", "nombre referencia 2"),
    "ref2_tipo_telefono": ("tipo telefono", "tipo telefono referencia 2"),
    "ref2_parentesco": ("parentesco", "parentesco referencia 2", "parentezco"),
    "ref3_nombre": ("nombre referencia 3", "ref3 nombre"),
    "ref3_tel": ("tel ref3", "tel ref 3", "telefono ref3"),
    "ref3_parentesco": ("parentesco referencia 3", "parentesco ref3"),
    "ref3_domicilio": ("domicilio referencia 3", "domicilio ref3"),
    "producto": ("producto",), "capital": ("monto original", "capital"),
    "fecha_credito": ("f otorgamiento", "fecha otorgamiento", "fecha credito", "fch credito"),
    "fecha_ult_pago_finore": (
        "f ultimo pago jun",
        "fecha ultimo pago jun",
        "f ultimo pago",
        "fecha ult pago en finore",
    ),
    "monto_ult_pago_finore": ("monto ult pago en finore", "monto ultimo pago en finore"),
    "mora_1": ("dias atraso 06 07", "dias atraso", "mora"),
    "dias_atraso_estimado": ("dias atraso est 31 08", "dias atraso estimado"),
    "pagos_atrasados_jun": ("pagos atrasados jun",), "deudas_vencidas_toku": ("deudas vencidas toku",),
    "capital_vencido": ("capital vencido",),
    "total": ("capital total", "total"), "intereses_vencidos": ("int vencidos", "intereses vencidos"),
    "moratorios": ("moratorios",), "sdo_actual": ("saldo 06 07", "saldo actual"),
    "pagado_agosto": ("pagado agosto",), "saldo_estimado_3108": ("saldo est", "saldo est 31 08", "saldo estimado 31 08"),
    "tramo": ("tramo",), "marca_interna": ("marca interna",),
    "celular": ("telefono", "celular", "telefono celular"),
    "casa": ("casa", "telefono casa"),
    "domicilio_completo": ("domicilio completo", "domicilio"), "calle_numero": ("calle", "calle numero"),
    "colonia": ("colonia",), "ciudad": ("municipio", "ciudad"), "estado": ("estado",),
    "codigo_postal": ("cp", "codigo postal"), "correo_cliente": ("correo", "correo cliente", "email"),
    "estatus_correo_cliente": ("estatus correo", "estatus correo cliente"),
    "estatus_mb": ("estatus mb",),
    "opcion_1_pago_unico": ("opcion 1 pago unico",),
    "ahorro_cliente": ("ahorro para el cliente",),
    "porcentaje_descuento": ("descuento", "porcentaje descuento"),
    "opcion_2_convenio_total": ("opcion 2 convenio total",),
    "abono_semanal": ("abono semanal",),
    "numero_semanas": ("no de semanas", "numero de semanas"),
    "oferta_especial_propuesta": ("oferta especial propuesta",),
    "vigencia": ("vigencia",),
    "sdo_capital": ("capital vigente", "saldo capital", "sdo capita"),
    "pagos_ptes": ("pagos ptes",), "pagos_pdtes_actual": ("pagos pdtes actual",),
    "erogacion": ("erogacion",), "pago_mensual": ("pago mens", "pago mensual"),
    "ventanilla": ("ventanilla",), "edad": ("edad",), "sucursal": ("sucursal",),
}
HEADER_TO_FIELDS: dict[str, list[str]] = {}
for field_name, headers in FIELD_HEADERS.items():
    for header in headers:
        HEADER_TO_FIELDS.setdefault(header, []).append(field_name)
REQUIRED_FIELDS = {"id_cuenta", "cliente"}

DATE_COLUMNS = {
    "fecha_asig",
    "fecha_prom",
    "fecha_credito",
    "fecha_ult_pago_finore",
    "fecha_arranque",
}

DECIMAL_COLUMNS = {
    "monto_prom",
    "proyeccion_cierre",
    "sdo_vencido_inicial",
    "saldo_vencido_actual",
    "capital",
    "deudas_vencidas_toku",
    "capital_vencido",
    "sdo_capital",
    "total",
    "intereses_vencidos",
    "moratorios",
    "sdo_actual",
    "pagado_agosto",
    "saldo_estimado_3108",
    "opcion_1_pago_unico",
    "ahorro_cliente",
    "porcentaje_descuento",
    "opcion_2_convenio_total",
    "abono_semanal",
    "monto_ult_pago_finore",
    "erogacion",
    "pago_mensual",
    "pagos_ago",
    "pagos_jul",
}

INTEGER_COLUMNS = {"numero_semanas", "pagos_ptes", "pagos_pdtes_actual", "edad", "gestiones"}
MAX_IMPORT_RECORDS = 100_000


class ImportFormatError(ValueError):
    """El archivo no coincide con el layout esperado."""


def normalize_header(value: object) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    text = " ".join(text.lower().split())
    text = re.sub(r"\bsaldo est \d{1,2} \d{1,2}\b", "saldo est", text)
    return text


def read_table(contents: bytes, filename: str) -> pd.DataFrame:
    extension = Path(filename).suffix.lower()
    if extension in {".xlsx", ".xlsm", ".xls"}:
        engine = "xlrd" if extension == ".xls" else "openpyxl"
        with pd.ExcelFile(BytesIO(contents), engine=engine) as workbook:
            for sheet_name in workbook.sheet_names:
                table = pd.read_excel(
                    workbook,
                    sheet_name=sheet_name,
                    header=None,
                    dtype=object,
                )
                try:
                    find_header_row(table)
                except ImportFormatError:
                    continue
                return table
        raise ImportFormatError(
            "No encontre una pestana con los encabezados de cartera requeridos."
        )

    if extension == ".csv":
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = contents.decode("cp1252")
        return pd.read_csv(
            StringIO(text),
            sep=None,
            engine="python",
            header=None,
            dtype=object,
            keep_default_na=False,
        )

    raise ImportFormatError("Formato no admitido. Usa .xlsx, .xls, .xlsm o .csv.")


def map_header_columns(header: list[object]) -> dict[str, int]:
    mapped = {}
    occurrences: dict[str, int] = {}
    generic_email_status_count = sum(
        normalize_header(value) == "estatus correo" for value in header
    )

    for position, value in enumerate(header):
        normalized = normalize_header(value)
        if normalized == "estatus correo" and generic_email_status_count == 1:
            mapped["estatus_correo_cliente"] = position
            continue

        candidates = HEADER_TO_FIELDS.get(normalized, [])
        occurrence = occurrences.get(normalized, 0)
        occurrences[normalized] = occurrence + 1
        if occurrence < len(candidates):
            mapped.setdefault(candidates[occurrence], position)
    return mapped


def find_header_row(table: pd.DataFrame) -> tuple[int, dict[str, int]]:
    for row_index in range(min(30, len(table.index))):
        mapped = map_header_columns(table.iloc[row_index].tolist())
        if REQUIRED_FIELDS.issubset(mapped):
            return row_index, mapped
    raise ImportFormatError("No se encontraron las tres columnas obligatorias en las primeras 30 filas: Clave Cliente, No. de Credito y Nombre cliente.")


def is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def excel_cell_to_text(value: object) -> str | None:
    if is_missing(value):
        return None

    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    elif hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass

    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    text = str(value).strip()
    return text or None


def normalize_text(value: object) -> str | None:
    text = excel_cell_to_text(value)
    if text is None:
        return None

    if text.upper() in {"#N/A", "N/A", "NA"}:
        return None
    return text


def normalize_decimal(value: object, row_number: int, column_name: str) -> str | None:
    value = excel_cell_to_text(value)
    if value is None:
        return None

    if value.upper() in {
        "#N/A",
        "N/A",
        "NA",
        "PDTE",
        "PENDIENTE",
        "-",
    }:
        return None

    text = re.sub(r"[^0-9,.-]", "", value)
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        decimals = len(text.rsplit(",", 1)[-1])
        text = text.replace(",", ".") if decimals in (1, 2) else text.replace(",", "")

    if not text or text in {"-", ".", ","}:
        expected_empty_values = {
            "#N/A",
            "N/A",
            "NA",
            "PDTE",
            "PENDIENTE",
            "-",
        }
        if str(value).strip().upper() not in expected_empty_values:
            logger.warning(
                "Valor no interpretable en fila %s, campo %s; se importará como NULL",
                row_number,
                column_name,
            )
        return None

    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
        if not amount.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        logger.warning(
            "Valor no válido en fila %s, campo %s; se importará como NULL",
            row_number,
            column_name,
        )
        return None

    return format(amount, ".2f")


def normalize_integer(value: object, row_number: int, column_name: str) -> str | None:
    value = excel_cell_to_text(value)
    if value is None:
        return None

    text = value.strip()
    if text.upper() in {"#N/A", "N/A", "NA", "PDTE", "PENDIENTE", "-", "—"}:
        return None
    if "," in text and "." not in text:
        decimal_places = len(text.rsplit(",", 1)[-1])
        text = text.replace(",", ".") if decimal_places in (1, 2) else text.replace(",", "")

    try:
        number = Decimal(text)
        if not number.is_finite():
            raise InvalidOperation
        number = number.to_integral_value(rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        logger.warning(
            "Valor no válido en fila %s, campo %s; se importará como NULL",
            row_number,
            column_name,
        )
        return None
    return str(int(number))


def normalize_date(value: object, row_number: int, column_name: str) -> str | None:
    value = excel_cell_to_text(value)
    if value is None:
        return None

    text = value.strip()
    if text.upper() in {"#N/A", "N/A", "NA", "PDTE", "PENDIENTE", "-"}:
        return None

    try:
        serial = Decimal(text)
        if serial.is_finite() and serial >= 1:
            excel_date = datetime(1899, 12, 30) + pd.to_timedelta(
                float(serial),
                unit="D",
            )
            return excel_date.date().isoformat()
    except (InvalidOperation, OverflowError, TypeError, ValueError):
        pass

    for date_format in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%Y/%m/%d",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue

    logger.warning(
        "Fecha no válida en fila %s, campo %s; se importará como NULL",
        row_number,
        column_name,
    )
    return None


def parse_cartera_file(contents: bytes, filename: str) -> list[dict[str, object]]:
    table = read_table(contents, filename)
    header_index, column_positions = find_header_row(table)
    records = []
    seen_credit_numbers = set()
    errors = []
    for row_index in range(header_index + 1, len(table.index)):
        row = table.iloc[row_index].tolist()
        if all(is_missing(value) or not str(value).strip() for value in row):
            continue
        record: dict[str, object] = {name: None for name in FIELD_HEADERS}
        for name, position in column_positions.items():
            value = row[position] if position < len(row) else None
            try:
                value = excel_cell_to_text(value)
                if name in INTEGER_COLUMNS:
                    record[name] = normalize_integer(value, row_index + 1, name)
                elif name in DECIMAL_COLUMNS:
                    record[name] = normalize_decimal(value, row_index + 1, name)
                elif name in DATE_COLUMNS:
                    record[name] = normalize_date(value, row_index + 1, name)
                else:
                    record[name] = normalize_text(value)
            except Exception:
                logger.exception(
                    "No se pudo leer fila %s, campo %s; se usará un valor seguro",
                    row_index + 1,
                    name,
                )
                record[name] = (
                    None
                    if name in INTEGER_COLUMNS | DECIMAL_COLUMNS | DATE_COLUMNS
                    else "ERROR DE DATO"
                )
        if not record.get("id_cuenta"):
            errors.append(f"fila {row_index + 1}: falta Clave Cliente")
            continue
        if not record.get("cliente"):
            errors.append(f"fila {row_index + 1}: falta Nombre cliente")
            continue
        # BORDER CREDIT incluye No. de Crédito; FINORE identifica sus cuentas
        # únicamente con IdCuenta. Conservamos cada dato en su campo original.
        import_key = record.get("numero_credito") or record["id_cuenta"]
        if import_key in seen_credit_numbers:
            errors.append(f"fila {row_index + 1}: identificador duplicado ({import_key})")
            continue
        seen_credit_numbers.add(import_key)
        record["clave_importacion"] = import_key
        records.append(record)
    if errors:
        preview = "; ".join(errors[:10])
        if len(errors) > 10:
            preview += f"; y {len(errors) - 10} errores mas"
        raise ImportFormatError(f"Corrige el archivo antes de importar: {preview}.")
    if not records:
        raise ImportFormatError("No encontre filas de cartera debajo del encabezado.")
    if len(records) > MAX_IMPORT_RECORDS:
        raise ImportFormatError(
            "El archivo supera el maximo de 100,000 cuentas por carga."
        )
    return records
