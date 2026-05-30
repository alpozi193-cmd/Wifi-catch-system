"""Uygulama ayarları yardımcıları."""

from __future__ import annotations

from database import SessionLocal
from models import AppSetting

DEFAULTS = {
    "alert_gb": "5.0",
}


def get_setting(key: str) -> str:
    db = SessionLocal()
    try:
        row = db.query(AppSetting).filter_by(key=key).first()
        if row:
            return row.value
        return DEFAULTS.get(key, "")
    finally:
        db.close()


def set_setting(key: str, value: str) -> None:
    db = SessionLocal()
    try:
        row = db.query(AppSetting).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()
