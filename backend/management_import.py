from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import re
from typing import TypedDict

import pandas as pd

if __package__:
    from .excel_import import (
        ImportFormatError,
        excel_cell_to_text,
        normalize_header,
        normalize_identifier,
    )
else:
    from excel_import import (
        ImportFormatError,
        excel_cell_to_text,
        normalize_header,
        normalize_identifier,
    )


MANAGEMENT_RESULTS = (
    "01.-Sin gestion",
    "02.-Pago parcial",
    "03.-Cuenta regularizada",
    "04.-Convenio Liquidacion",
    "05.-Promesa de Pago",
    "06.-Convenio roto",
    "07.-Promesa incumplida",
    "08.-Seguimiento",
    "09.-Mnje con fam",
    "10.- Mnje trabajo",
    "11.-Mnje con ref",
    "12.-Liquidacion",
    "13.-No contesta",
    "14.-Buzon",
    "15.-No lo conoce",
    "16.-Fuera de servicio",
    "17.-No enlaza",
    "18.-Defuncion",
    "19.-Cliente evasivo",
    "20.-Negativa",
    "21.-Aclaracion",
    "22.-Retiro x financiera",
)

RESULTS_BY_DESCRIPTION = {
    normalize_header(result.split("-", maxsplit=1)[1]): result
    for result in MANAGEMENT_RESULTS
}

COLUMN_ALIASES = {
    "numero_credito": {"no credito", "numero credito", "nocredito", "numcredito"},
    "resultado": {"estatus credito", "estatus general", "resultado"},
    "fecha": {"fecha de la gestion", "fecha gestion", "fecha"},
    "comentario_nuevo": {"comentario general nuevo", "comentario nuevo"},
    "comentario_anterior": {"comentario general anterior", "comentario anterior"},
    "telefono": {"telefono marcado", "telefono"},
}
REQUIRED_COLUMNS = {"numero_credito", "resultado", "fecha"}
IGNORED_RESULTS = {"N/A", "NA", "#N/A", "#REF!", "NAN", "NONE"}
MAX_IMPORT_RECORDS = 100_000


class ManagementImportRecord(TypedDict):
    numero_credito: str
    codigo_resultado: str
    fecha_gestion: str
    comentario: str | None
    telefono_contactado: str | None
    fila_origen: int


class ParsedManagementFile(TypedDict):
    records: list[ManagementImportRecord]
    registros_leidos: int
    omitidas_sin_resultado: int
    omitidas_sin_credito: int
    omitidas_sin_fecha: int


def normalize_management_result(value: object) -> str | None:
    text = excel_cell_to_text(value)
    if text is None:
        return None

    text = text.strip()
    if text.upper() in IGNORED_RESULTS or text.startswith("#"):
        return None

    description = re.sub(r"^\s*\d{1,2}\s*\.?\s*-\s*", "", text)
    description = description.replace("\ufffd", "o")
    normalized_description = normalize_header(description)
    result = RESULTS_BY_DESCRIPTION.get(normalized_description)
    if result:
        return result

    raise ImportFormatError(
        f"El resultado de gestión «{text}» no está en el catálogo en fila del archivo."
    )


def normalize_management_datetime(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(sep=" ")
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat(sep=" ")

    text = str(value).strip()
    if not text:
        return None

    try:
        serial = float(text)
        if 0 < serial < 2_958_466:
            return (
                datetime(1899, 12, 30) + timedelta(days=serial)
            ).isoformat(sep=" ")
    except ValueError:
        pass

    for date_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(text, date_format).isoformat(sep=" ")
        except ValueError:
            continue
    return None


def parse_gestiones_file(
    contents: bytes,
    filename: str,
) -> ParsedManagementFile:
    extension = Path(filename).suffix.lower()
    if extension not in {".xlsx", ".xlsm", ".xls"}:
        raise ImportFormatError("Formato no admitido. Usa .XLSX, .XLSM o .XLS.")

    engine = "xlrd" if extension == ".xls" else "openpyxl"
    try:
        with pd.ExcelFile(BytesIO(contents), engine=engine) as workbook:
            sheet_name = next(
                (
                    name
                    for name in workbook.sheet_names
                    if name.strip().casefold() == "gestiones"
                ),
                None,
            )
            if sheet_name is None:
                raise ImportFormatError(
                    "No encontré la pestaña «Gestiones» en el archivo."
                )
            table = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                dtype=object,
            )
    except ImportFormatError:
        raise
    except (ValueError, OSError, ImportError) as exc:
        raise ImportFormatError(
            "No se pudo leer la pestaña «Gestiones» del archivo."
        ) from exc

    positions: dict[str, int] = {}
    for position, header in enumerate(table.columns):
        normalized = normalize_header(header)
        for field, aliases in COLUMN_ALIASES.items():
            if normalized in aliases:
                positions.setdefault(field, position)

    missing_columns = REQUIRED_COLUMNS - positions.keys()
    if missing_columns:
        raise ImportFormatError(
            "Faltan encabezados requeridos en la pestaña «Gestiones»: "
            + ", ".join(sorted(missing_columns))
            + "."
        )

    records: list[ManagementImportRecord] = []
    skipped_without_result = 0
    skipped_without_credit = 0
    skipped_without_date = 0

    for row_index, row in table.iterrows():
        result_value = row.iloc[positions["resultado"]]
        try:
            result = normalize_management_result(result_value)
        except ImportFormatError as exc:
            raise ImportFormatError(
                f"{exc} Fila Excel {int(row_index) + 2}."
            ) from exc
        if result is None:
            skipped_without_result += 1
            continue

        credit_number = normalize_identifier(row.iloc[positions["numero_credito"]])
        if credit_number is None:
            skipped_without_credit += 1
            continue

        management_date = normalize_management_datetime(row.iloc[positions["fecha"]])
        if management_date is None:
            skipped_without_date += 1
            continue

        comment = None
        for field in ("comentario_nuevo", "comentario_anterior"):
            position = positions.get(field)
            if position is not None:
                comment = excel_cell_to_text(row.iloc[position])
                if comment and comment.upper() not in IGNORED_RESULTS:
                    break
                comment = None

        phone_position = positions.get("telefono")
        phone = (
            normalize_identifier(row.iloc[phone_position])
            if phone_position is not None
            else None
        )
        if phone and phone.upper() in IGNORED_RESULTS:
            phone = None

        records.append({
            "numero_credito": credit_number,
            "codigo_resultado": result,
            "fecha_gestion": management_date,
            "comentario": comment,
            "telefono_contactado": phone,
            "fila_origen": int(row_index) + 2,
        })

    if len(records) > MAX_IMPORT_RECORDS:
        raise ImportFormatError(
            "El archivo supera el máximo de 100,000 gestiones por carga."
        )
    if not records:
        raise ImportFormatError(
            "No encontré gestiones con resultado, crédito y fecha válidos."
        )

    return {
        "records": records,
        "registros_leidos": len(table.index),
        "omitidas_sin_resultado": skipped_without_result,
        "omitidas_sin_credito": skipped_without_credit,
        "omitidas_sin_fecha": skipped_without_date,
    }
