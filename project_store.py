# tools/project_store.py
# ----------------------
# Αποθήκευση / Φόρτωση Project σε JSON
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from settings.project_state import (
    PROJECT_SETTINGS,
    DEFAULT_PROJECT_SETTINGS,
    ensure_project_settings,
)
from settings.selections import INSTRUMENT_DATA

SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = {1, 2}


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_projects_dir() -> Path:
    """
    Windows default:
    C:\\Users\\<user>\\Documents\\Arito\\Projects
    """
    return Path.home() / "Documents" / "Arito" / "Projects"


def default_project_path(filename: str = "last_project.json") -> Path:
    return default_projects_dir() / filename


def _to_jsonable(obj: Any) -> Any:
    """
    Μετατρέπει αντικείμενα σε JSON-serializable μορφή.
    Καλύπτει dict/list/tuple/set + βασικούς τύπους.
    """
    if obj is None:
        return None
    if isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]

    if isinstance(obj, set):
        try:
            return sorted([_to_jsonable(x) for x in obj])
        except Exception:
            return [_to_jsonable(x) for x in obj]

    # fallback: string
    return str(obj)


def export_project_dict() -> Dict[str, Any]:
    """
    Πακετάρει το INSTRUMENT_DATA σε ένα dict με schema/version.
    """
    slots = {str(k): _to_jsonable(v) for k, v in INSTRUMENT_DATA.items()}
    return {
        "schema_version": SCHEMA_VERSION,
        "saved_at_utc": _now_iso_utc(),
        "project_settings": _to_jsonable(ensure_project_settings()),
        "slots": slots,
    }


def import_project_dict(data: Dict[str, Any]) -> None:
    """
    Φορτώνει τα slots μέσα στο INSTRUMENT_DATA.
    """
    if not isinstance(data, dict):
        raise ValueError("Το JSON αρχείο δεν είναι dict.")

    ver = int(data.get("schema_version", 0))
    if ver not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Μη υποστηριζόμενο schema_version: {ver}")

    slots = data.get("slots", {})
    if not isinstance(slots, dict):
        raise ValueError("Λείπει ή είναι λάθος το πεδίο 'slots'.")

    PROJECT_SETTINGS.clear()
    PROJECT_SETTINGS.update(DEFAULT_PROJECT_SETTINGS)
    raw_settings = data.get("project_settings", {})
    if isinstance(raw_settings, dict):
        PROJECT_SETTINGS.update(raw_settings)
    ensure_project_settings()

    INSTRUMENT_DATA.clear()

    for k, v in slots.items():
        try:
            idx = int(k)
        except Exception:
            continue
        if isinstance(v, dict):
            INSTRUMENT_DATA[idx] = v
        else:
            INSTRUMENT_DATA[idx] = {"data": v}


def save_project(path: str | Path | None = None) -> Path:
    """
    Σώζει JSON στο path ή στο default Documents/Arito/Projects/last_project.json
    """
    p = Path(path) if path else default_project_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    data = export_project_dict()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_project(path: str | Path | None = None) -> Path:
    """
    Φορτώνει JSON από path ή default.
    """
    p = Path(path) if path else default_project_path()
    if not p.exists():
        raise FileNotFoundError(f"Δεν βρέθηκε project: {p}")

    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)

    import_project_dict(data)
    return p
