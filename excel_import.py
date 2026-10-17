from csv import Sniffer, reader
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
import re
import unicodedata


HEADER_POSITIONS = {
    0: "id_cuenta",
    1: "numero_credito",
    2: "estatus_promesa_act",
    3: "estatus_promesa_ant",
    4: "asignacion",
    5: "agente_texto",
    6: "campanas",
    7: "prioridad",
    8: "cliente",
    9: "estatus",
    10: "ult_gestion",
    11: "frecuencia",
    12: "comentario",
    13: "excel_pagos",
    14: "rec_mb",
    15: "fecha_prom",
    16: "monto_prom",
    17: "proyeccion_cierre",
    18: "sdo_vencido_inicial",
    19: "saldo_vencido_actual",
    20: "pagos_sep",
    21: "empresa_pagadora",
    22: "telempresa",
    23: "correo_empresa",
    24: "estatus_correo_empresa",
    25: "referencia_1",
    26: "ref1_nombre",
    27: "ref1_tipo_telefono",
    28: "ref1_parentesco",
    29: "referencia_2",
    30: "en_predic",
    31: "ref2_nombre",
    32: "ref2_tipo_telefono",
    33: "ref2_parentesco",
    34: "producto",
    35: "capital",
    36: "fecha_credito",
    37: "fecha_ult_pago_finore",
    38: "mora_1",
    39: "dias_atraso_estimado",
    40: "pagos_atrasados_jun",
    41: "deudas_vencidas_toku",
    42: "capital_vencido",
    43: "sdo_capital",
    44: "total",
    45: "intereses_vencidos",
    46: "moratorios",
    47: "sdo_actual",
    48: "pagado_agosto",
    49: "saldo_estimado_3108",
    50: "tramo",
    51: "marca_interna",
    52: "celular",
    53: "domicilio_completo",
    54: "calle_numero",
    55: "colonia",
    56: "ciudad",
    57: "estado",
    58: "codigo_postal",
    59: "correo_cliente",
    60: "estatus_correo_cliente",
    62: "estatus_mb",
    63: "campana",
}

DATE_COLUMNS = {
    "fecha_prom",
    "fecha_credito",
    "fecha_ult_pago_finore",
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
}

REQUIRED_HEADERS = {
    0: "clave cliente",
    1: "no de credito",
    8: "nombre cliente",
    52: "telefono",
    62: "estatus mb",
    63: "campanas mb",
}


class ImportFormatError(ValueError):
    """El archivo no coincide con el layout esperado."""


def normalize_header(value: object) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    return " ".join(text.lower().split())


def read_rows(contents: bytes, filename: str) -> list[tuple[object, ...]]:
    extension = Path(filename).suffix.lower()

    if extension in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        workbook = load_workbook(BytesIO(contents), read_only=True, data_only=True)
        worksheet = workbook.active
        rows = [tuple(row) for row in worksheet.iter_rows(values_only=True)]
        workbook.close()
        return rows

    if extension == ".xls":
        import xlrd

        workbook = xlrd.open_workbook(file_contents=contents, on_demand=True)
        worksheet = workbook.sheet_by_index(0)
        rows = []
        for row_index in range(worksheet.nrows):
            values = []
            for cell in worksheet.row(row_index):
                if cell.ctype == xlrd.XL_CELL_DATE:
                    values.append(xlrd.xldate_as_datetime(cell.value, workbook.datemode))
                else:
                    values.append(cell.value)
            rows.append(tuple(values))
        workbook.release_resources()
        return rows

    if extension == ".csv":
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = contents.decode("cp1252")

        sample = text[:8192]
        try:
            delimiter = Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except Exception:
            delimiter = ","

        return [tuple(row) for row in reader(StringIO(text), delimiter=delimiter)]

    raise ImportFormatError("Formato no admitido. Usa .xlsx, .xls, .xlsm o .csv.")


def find_header_row(rows: list[tuple[object, ...]]) -> int:
    for row_index, row in enumerate(rows[:30]):
        normalized = [normalize_header(cell) for cell in row]
        if all(
            position < len(normalized)
            and normalized[position] == expected
            for position, expected in REQUIRED_HEADERS.items()
        ):
            return row_index

    raise ImportFormatError(
        "No encontré el encabezado esperado en las primeras 30 filas. "
        "Verifica que sea el layout compartido y que las columnas no estén reordenadas."
    )


def normalize_text(value: object) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    text = str(value).strip()
    return text or None


def normalize_decimal(value: object, row_number: int, column_name: str) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    text = str(value).strip()
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    else:
        text = re.sub(r"[^0-9,.-]", "", text)
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            decimals = len(text.rsplit(",", 1)[-1])
            text = text.replace(",", ".") if decimals in (1, 2) else text.replace(",", "")

    if not text:
        return None

    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
        if not amount.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise ImportFormatError(
            f"El valor de {column_name} en la fila {row_number} no es un importe válido."
        ) from None

    return format(amount, ".2f")


def normalize_date(value: object, row_number: int, column_name: str) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue

    raise ImportFormatError(
        f"La fecha de {column_name} en la fila {row_number} no tiene un formato reconocido."
    )


def parse_cartera_file(contents: bytes, filename: str) -> list[dict[str, object]]:
    rows = read_rows(contents, filename)
    header_index = find_header_row(rows)
    records = []
    seen_credit_numbers = set()
    errors = []

    for row_index, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not any(value is not None and str(value).strip() for value in row):
            continue

        record: dict[str, object] = {}
        for position, column_name in HEADER_POSITIONS.items():
            value = row[position] if position < len(row) else None
            if column_name in DECIMAL_COLUMNS:
                record[column_name] = normalize_decimal(value, row_index, column_name)
            elif column_name in DATE_COLUMNS:
                record[column_name] = normalize_date(value, row_index, column_name)
            else:
                record[column_name] = normalize_text(value)

        if not record.get("id_cuenta"):
            errors.append(f"fila {row_index}: falta Clave Cliente")
            continue
        if not record.get("numero_credito"):
            errors.append(f"fila {row_index}: falta No. de Crédito")
            continue
        if not record.get("cliente"):
            errors.append(f"fila {row_index}: falta Nombre cliente")
            continue

        credit_number = record["numero_credito"]
        if credit_number in seen_credit_numbers:
            errors.append(f"fila {row_index}: No. de Crédito duplicado ({credit_number})")
            continue

        seen_credit_numbers.add(credit_number)
        records.append(record)

    if errors:
        preview = "; ".join(errors[:10])
        if len(errors) > 10:
            preview += f"; y {len(errors) - 10} errores más"
        raise ImportFormatError(f"Corrige el archivo antes de importar: {preview}.")

    if not records:
        raise ImportFormatError("No encontré filas de cartera debajo del encabezado.")
    if len(records) > 10000:
        raise ImportFormatError("El archivo supera el máximo de 10,000 cuentas por carga.")

    return records




