"""CSV/JSON normalization with versionable column mappings; no EPS hardcodes."""
import csv
import io
import json
from datetime import date
from typing import Any
from fastapi import HTTPException
from pydantic import ValidationError
from .schemas import AccountInput

MAX_FILE_SIZE = 4_000_000
MAX_ROWS = 500
ALLOWED_TARGETS = {"account_ref", "payer", "modality", "service_type", "issued_on"}

def read_rows(data: bytes, filename: str):
    if not data or len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, "Archivo vacío o superior a 4 MB")
    try:
        text = data.decode("utf-8-sig")
        if filename.lower().endswith(".csv"):
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            keys = list(reader.fieldnames or [])
        elif filename.lower().endswith(".json"):
            payload = json.loads(text)
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict):
                rows = payload.get("accounts", payload.get("objections", []))
            else:
                raise ValueError("JSON must contain an accounts array")
            keys = sorted({key for row in rows if isinstance(row, dict) for key in row})
        else:
            raise HTTPException(415, "Solo archivos CSV o JSON en este hito")
    except (UnicodeDecodeError, ValueError, TypeError, csv.Error):
        raise HTTPException(422, "Archivo CSV/JSON no legible") from None
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS or any(not isinstance(r, dict) for r in rows):
        raise HTTPException(422, "Se requiere una lista de entre 1 y 500 registros")
    return keys, rows

def normalize(rows: list[dict], columns: dict[str, str]):
    if "account_ref" not in columns:
        raise HTTPException(422, "El mapeo debe definir account_ref")
    for key in columns:
        if key not in ALLOWED_TARGETS and not key.startswith("facts."):
            raise HTTPException(422, "Campo de destino no permitido: " + key)
    accepted = []
    problems = []
    for index, row in enumerate(rows, 1):
        result: dict[str, Any] = {"facts": {}}
        for target, source in columns.items():
            value = row.get(source)
            if value is None or value == "": continue
            if target.startswith("facts."):
                current = result["facts"]
                path = target.split(".")[1:]
                if not path or any(not piece or piece.startswith("_") for piece in path):
                    raise HTTPException(422, "Ruta de mapeo inválida")
                for key in path[:-1]:
                    current = current.setdefault(key, {})
                current[path[-1]] = value
            else:
                result[target] = value
        try:
            accepted.append(AccountInput.model_validate(result).model_dump(mode="json"))
        except ValidationError as exc:
            problems.append({"row": index, "issue": exc.errors()[0]["msg"]})
    return {"rows": accepted, "errors": problems, "total": len(rows), "accepted": len(accepted)}

OBJECTION_TARGETS = {"objection_ref", "kind", "code", "description", "amount",
                     "account_ref", "payer", "modality", "service_type", "issued_on"}

def normalize_objections(rows: list[dict], columns: dict[str, str]):
    """Interpret heterogeneous EPS exports without guessing causals or types."""
    from .schemas import ObjectionInput
    for required in ("objection_ref", "kind", "description", "account_ref"):
        if required not in columns:
            raise HTTPException(422, "Falta el mapeo obligatorio: " + required)
    for target in columns:
        if target not in OBJECTION_TARGETS and not target.startswith("facts."):
            raise HTTPException(422, "Destino de objeción no permitido: " + target)
    accepted, problems = [], []
    for index, row in enumerate(rows, 1):
        objection = {"account": {"facts": {}}}
        for target, source in columns.items():
            value = row.get(source)
            if value is None or value == "": continue
            if target.startswith("facts."):
                current = objection["account"]["facts"]
                path = target.split(".")[1:]
                if not path or any(not p or p.startswith("_") for p in path):
                    raise HTTPException(422, "Ruta de mapeo inválida")
                for part in path[:-1]: current = current.setdefault(part, {})
                current[path[-1]] = value
            elif target in {"account_ref", "payer", "modality", "service_type", "issued_on"}:
                objection["account"][target] = value
            elif target == "kind":
                standard = str(value).strip().upper().replace("Ó", "O")
                objection[target] = {"G": "GLOSA", "D": "DEVOLUCION", "DEV": "DEVOLUCION"}.get(standard, standard)
            else:
                objection[target] = value
        try:
            accepted.append(ObjectionInput.model_validate(objection).model_dump(mode="json"))
        except ValidationError as exc:
            problems.append({"row": index, "issue": exc.errors()[0]["msg"]})
    return {"rows": accepted, "errors": problems, "total": len(rows), "accepted": len(accepted)}
