"""
Flask ana sunucu: agent API + web arayüzü.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# server/ içinden models ve database
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import SessionLocal, init_db
from models import AgentReport, AppSetting, Device, TrafficLog, User, WifiNetwork
from settings_util import get_setting, set_setting

WEB_ROOT = Path(__file__).resolve().parent.parent / "web_interface"
AGENT_TOKEN = os.environ.get("EV_AGI_AGENT_TOKEN", "")
MODEM_STALE_SECONDS = int(os.environ.get("EV_AGI_MODEM_STALE", "300"))

app = Flask(
    __name__,
    template_folder=str(WEB_ROOT / "templates"),
    static_folder=str(WEB_ROOT / "static"),
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "degistir-bu-anahtari")


def get_db_session():
    return SessionLocal()


def require_agent_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if AGENT_TOKEN:
            token = request.headers.get("X-Agent-Token", "")
            if token != AGENT_TOKEN:
                return jsonify({"error": "Yetkisiz agent"}), 401
        return f(*args, **kwargs)

    return decorated


@app.before_request
def ensure_db():
    if not getattr(app, "_db_ready", False):
        init_db()
        app._db_ready = True
        _seed_demo_user()


def _seed_demo_user():
    db = get_db_session()
    try:
        if not db.query(User).filter_by(username="admin").first():
            db.add(
                User(
                    username="admin",
                    password_hash=generate_password_hash("admin"),
                )
            )
            db.commit()
    finally:
        db.close()


# --- Web sayfaları ---


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db_session()
        try:
            user = db.query(User).filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                session["username"] = user.username
                return redirect(url_for("dashboard"))
            error = "Kullanıcı adı veya şifre hatalı"
        finally:
            db.close()
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if len(username) < 3:
            error = "Kullanıcı adı en az 3 karakter olmalı"
        elif len(username) > 80:
            error = "Kullanıcı adı çok uzun"
        elif len(password) < 6:
            error = "Şifre en az 6 karakter olmalı"
        elif password != password2:
            error = "Şifreler eşleşmiyor"
        else:
            db = get_db_session()
            try:
                if db.query(User).filter_by(username=username).first():
                    error = "Bu kullanıcı adı zaten alınmış"
                else:
                    db.add(
                        User(
                            username=username,
                            password_hash=generate_password_hash(password),
                        )
                    )
                    db.commit()
                    flash("Hesap oluşturuldu. Giriş yapabilirsiniz.", "success")
                    return redirect(url_for("login"))
            finally:
                db.close()

    return render_template("register.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _today_bytes(db) -> int:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    logs = db.query(TrafficLog).filter(TrafficLog.recorded_at >= start).all()
    return sum(l.bytes_delta or 0 for l in logs)


@app.route("/dashboard/device/<int:device_id>/label", methods=["POST"])
def device_label(device_id: int):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    label = request.form.get("label", "").strip()[:120]
    db = get_db_session()
    try:
        dev = db.query(Device).filter_by(id=device_id).first()
        if dev:
            dev.label = label
            db.commit()
            flash(f"Cihaz adı güncellendi: {label or '(boş)'}", "success")
    finally:
        db.close()
    return redirect(url_for("dashboard"))


@app.route("/dashboard/settings", methods=["POST"])
def dashboard_settings():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    alert_gb = request.form.get("alert_gb", "5").strip()
    try:
        float(alert_gb)
        set_setting("alert_gb", alert_gb)
        flash(f"Uyarı eşiği: {alert_gb} GB", "success")
    except ValueError:
        flash("Geçersiz GB değeri", "error")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    db = get_db_session()
    try:
        devices = (
            db.query(Device)
            .order_by(Device.total_bytes.desc(), Device.last_seen.desc())
            .all()
        )
        logs = (
            db.query(TrafficLog)
            .order_by(TrafficLog.recorded_at.desc())
            .limit(100)
            .all()
        )
        total_gb = sum(d.total_bytes or 0 for d in devices) / (1024 ** 3)
        today_gb = _today_bytes(db) / (1024 ** 3)
        alert_threshold = float(get_setting("alert_gb") or "5")
        alert_devices = [
            d
            for d in devices
            if (d.total_bytes or 0) / (1024**3) >= alert_threshold
        ]
        devices_with_usage = sum(1 for d in devices if (d.total_bytes or 0) > 0)
        wifi_networks = (
            db.query(WifiNetwork)
            .order_by(WifiNetwork.signal.desc(), WifiNetwork.scanned_at.desc())
            .limit(50)
            .all()
        )
        chart_slice = list(reversed(logs[-30:]))
        chart_labels = [
            l.recorded_at.strftime("%d.%m %H:%M") if l.recorded_at else "—"
            for l in chart_slice
        ]
        chart_values = [round(l.gb_total, 4) for l in chart_slice]
        last_report = (
            db.query(AgentReport).order_by(AgentReport.created_at.desc()).first()
        )
        last_modem = (
            db.query(AgentReport)
            .filter_by(report_type="modem")
            .order_by(AgentReport.created_at.desc())
            .first()
        )
        agent_connected = False
        if last_report and last_report.created_at:
            age = (datetime.utcnow() - last_report.created_at).total_seconds()
            agent_connected = age < 180
        modem_connected = False
        if last_modem and last_modem.created_at:
            age = (datetime.utcnow() - last_modem.created_at).total_seconds()
            modem_connected = age < MODEM_STALE_SECONDS
        monitor_ips: list = []
        last_traffic = (
            db.query(AgentReport)
            .filter_by(report_type="traffic")
            .order_by(AgentReport.created_at.desc())
            .first()
        )
        if last_traffic and last_traffic.payload:
            try:
                pl = json.loads(last_traffic.payload)
                monitor_ips = pl.get("monitor_ips") or []
            except json.JSONDecodeError:
                pass
        return render_template(
            "dashboard.html",
            devices=devices,
            logs=logs,
            total_gb=round(total_gb, 2),
            chart_labels=chart_labels or ["—"],
            chart_values=chart_values or [0],
            username=session.get("username"),
            agent_connected=agent_connected,
            last_report_at=last_report.created_at if last_report else None,
            last_report_str=(
                last_report.created_at.strftime("%d.%m.%Y %H:%M")
                if last_report and last_report.created_at
                else "—"
            ),
            devices_with_usage=devices_with_usage,
            modem_connected=modem_connected,
            monitor_ips=monitor_ips,
            today_gb=round(today_gb, 3),
            alert_threshold=alert_threshold,
            alert_devices=alert_devices,
            wifi_networks=wifi_networks,
        )
    finally:
        db.close()


# --- Agent API ---


@app.route("/api/agent/devices", methods=["POST"])
@require_agent_token
def api_devices():
    data = request.get_json(force=True, silent=True) or {}
    devices = data.get("devices", [])
    db = get_db_session()
    try:
        for item in devices:
            mac = item.get("mac", "")
            ip = item.get("ip", "")
            hostname = item.get("hostname", "")
            dev = db.query(Device).filter_by(mac=mac).first()
            if dev:
                dev.ip = ip
                dev.hostname = hostname
                dev.last_seen = datetime.utcnow()
            else:
                db.add(
                    Device(ip=ip, mac=mac, hostname=hostname, last_seen=datetime.utcnow())
                )
        db.add(
            AgentReport(
                report_type="devices",
                payload=json.dumps(devices, ensure_ascii=False),
            )
        )
        db.commit()
        return jsonify({"ok": True, "count": len(devices)})
    finally:
        db.close()


def _apply_usage_rows(db, usage: list, default_source: str = "pc") -> None:
    for row in usage:
        ip = row.get("ip", "")
        mac = row.get("mac", "")
        nbytes = int(row.get("bytes_delta", row.get("bytes", 0)))
        if nbytes <= 0:
            continue
        dev = None
        if mac:
            dev = db.query(Device).filter_by(mac=mac).first()
        if not dev and ip:
            dev = db.query(Device).filter_by(ip=ip).first()
        if dev:
            dev.total_bytes = (dev.total_bytes or 0) + nbytes
            if row.get("hostname"):
                dev.hostname = row.get("hostname") or dev.hostname
            dev.last_seen = datetime.utcnow()
        elif ip and mac:
            dev = Device(
                ip=ip,
                mac=mac,
                hostname=row.get("hostname", ""),
                total_bytes=nbytes,
                last_seen=datetime.utcnow(),
            )
            db.add(dev)
            db.flush()
        db.add(
            TrafficLog(
                device_id=dev.id if dev else None,
                ip=ip or (dev.ip if dev else ""),
                bytes_delta=nbytes,
                gb_total=nbytes / (1024 ** 3),
            )
        )


@app.route("/api/agent/modem", methods=["POST"])
@require_agent_token
def api_modem():
    """Modemden gelen cihaz listesi + trafik deltaları."""
    data = request.get_json(force=True, silent=True) or {}
    devices = data.get("devices", [])
    usage = data.get("usage", [])
    method = data.get("modem_method", "")
    db = get_db_session()
    try:
        for item in devices:
            mac = item.get("mac", "")
            ip = item.get("ip", "") or "0.0.0.0"
            hostname = item.get("hostname", "")
            if mac.startswith("unknown:"):
                continue
            dev = db.query(Device).filter_by(mac=mac).first()
            if dev:
                if ip and ip != "0.0.0.0":
                    dev.ip = ip
                if hostname:
                    dev.hostname = hostname
                dev.last_seen = datetime.utcnow()
            else:
                db.add(
                    Device(
                        ip=ip if ip != "0.0.0.0" else "192.168.0.0",
                        mac=mac,
                        hostname=hostname or "Modem",
                        last_seen=datetime.utcnow(),
                    )
                )
        _apply_usage_rows(db, usage, "modem")
        db.add(
            AgentReport(
                report_type="modem",
                payload=json.dumps(
                    {"devices": len(devices), "usage": len(usage), "method": method},
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
        return jsonify({"ok": True, "devices": len(devices), "usage": len(usage)})
    finally:
        db.close()


@app.route("/api/agent/wifi", methods=["POST"])
@require_agent_token
def api_wifi():
    data = request.get_json(force=True, silent=True) or {}
    networks = data.get("networks", [])
    db = get_db_session()
    try:
        db.query(WifiNetwork).delete()
        for n in networks:
            db.add(
                WifiNetwork(
                    ssid=n.get("ssid", "")[:128],
                    bssid=n.get("bssid", "")[:17],
                    signal=int(n.get("signal", 0)),
                    channel=str(n.get("channel", ""))[:16],
                    security=str(n.get("security", ""))[:64],
                    band=str(n.get("band", ""))[:32],
                    likely_extender=1 if n.get("likely_extender") else 0,
                )
            )
        db.add(
            AgentReport(
                report_type="wifi",
                payload=json.dumps({"count": len(networks)}, ensure_ascii=False),
            )
        )
        db.commit()
        return jsonify({"ok": True, "count": len(networks)})
    finally:
        db.close()


@app.route("/api/agent/traffic", methods=["POST"])
@require_agent_token
def api_traffic():
    data = request.get_json(force=True, silent=True) or {}
    usage = data.get("usage", [])
    total_gb = float(data.get("total_gb", 0))
    db = get_db_session()
    try:
        _apply_usage_rows(db, usage, "pc")

        db.add(
            AgentReport(
                report_type="traffic",
                payload=json.dumps(
                    {
                        "usage": usage,
                        "total_gb": total_gb,
                        "monitor_ips": data.get("monitor_ips", []),
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@app.route("/api/stats")
def api_stats():
    if not session.get("user_id"):
        return jsonify({"error": "Giriş gerekli"}), 401
    db = get_db_session()
    try:
        devices = db.query(Device).all()
        return jsonify(
            {
                "devices": [
                    {
                        "ip": d.ip,
                        "mac": d.mac,
                        "hostname": d.hostname,
                        "label": d.label,
                        "gb": round(d.total_bytes / (1024 ** 3), 3),
                        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                    }
                    for d in devices
                ]
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
