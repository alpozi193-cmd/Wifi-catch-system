"""
Ev ağı agent: tarama + PC trafiği + modem verisi -> Flask sunucu.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional, Set

import requests

from modem_client import (
    MODEM_ENABLED,
    fetch_modem_devices,
    modem_devices_to_dict,
    modem_usage_deltas,
)
from scanner import devices_to_dict, scan_network
from traffic import TrafficMonitor, get_local_ips
from wifi_scan import scan_wifi_networks, wifi_to_dict

DEFAULT_SERVER = os.environ.get("EV_AGI_SERVER", "http://127.0.0.1:5000")
AGENT_TOKEN = os.environ.get("EV_AGI_AGENT_TOKEN", "")
SCAN_INTERVAL = int(os.environ.get("EV_AGI_SCAN_INTERVAL", "300"))
TRAFFIC_REPORT_INTERVAL = int(os.environ.get("EV_AGI_TRAFFIC_INTERVAL", "60"))
MODEM_INTERVAL = int(os.environ.get("EV_AGI_MODEM_INTERVAL", "120"))
WIFI_INTERVAL = int(os.environ.get("EV_AGI_WIFI_INTERVAL", "300"))

_known_ips: Set[str] = set()


def post_json(url: str, payload: dict) -> bool:
    headers = {"Content-Type": "application/json"}
    if AGENT_TOKEN:
        headers["X-Agent-Token"] = AGENT_TOKEN
    for attempt in range(3):
        try:
            r = requests.post(url, data=json.dumps(payload), headers=headers, timeout=15)
            r.raise_for_status()
            return True
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2)
                continue
            hint = ""
            if "10061" in str(e) or "Connection refused" in str(e):
                hint = " -> Önce başka terminalde .\\run-server.ps1 çalıştırın."
            print(f"[agent] Gönderim hatası ({url}): {e}{hint}")
            return False
    return False


def send_devices(server: str, monitor: TrafficMonitor) -> bool:
    global _known_ips
    devices = scan_network()
    _known_ips = {d.ip for d in devices}
    monitor.set_known_ips(_known_ips)
    payload = {"devices": devices_to_dict(devices)}
    ok = post_json(f"{server.rstrip('/')}/api/agent/devices", payload)
    if ok:
        print(f"[agent] {len(devices)} cihaz listelendi (PC taraması)")
    return ok


def send_modem(server: str) -> bool:
    if not MODEM_ENABLED:
        return False
    devices, method = fetch_modem_devices()
    if not devices:
        return False
    usage = modem_usage_deltas(devices)
    payload = {
        "devices": modem_devices_to_dict(devices),
        "usage": usage,
        "modem_method": method,
    }
    ok = post_json(f"{server.rstrip('/')}/api/agent/modem", payload)
    if ok:
        print(f"[agent] Modem -> {len(devices)} cihaz, {len(usage)} trafik kaydı")
    return ok


def send_wifi(server: str) -> bool:
    networks = scan_wifi_networks()
    if not networks:
        return False
    ok = post_json(
        f"{server.rstrip('/')}/api/agent/wifi",
        {"networks": wifi_to_dict(networks)},
    )
    if ok:
        print(f"[agent] Wi-Fi -> {len(networks)} ag listelendi")
    return ok


def send_traffic(server: str, monitor: TrafficMonitor) -> None:
    usage = monitor.usage_report()
    payload = {
        "usage": usage,
        "total_gb": round(sum(u["bytes_delta"] for u in usage) / (1024**3), 4),
        "monitor_ips": list(monitor.local_ips),
        "source": "pc",
    }
    post_json(f"{server.rstrip('/')}/api/agent/traffic", payload)
    if usage:
        for row in usage[:3]:
            print(f"  [pc] {row['ip']}: {row['gb']} GB")
    print(f"[agent] PC trafik raporu -> {len(usage)} IP")


def run(server: Optional[str] = None, interface: Optional[str] = None) -> None:
    base = server or DEFAULT_SERVER
    local_ips = get_local_ips()
    monitor = TrafficMonitor(interface=interface, local_ips=local_ips)
    monitor.start()

    last_scan = 0.0
    last_traffic = 0.0
    last_modem = 0.0
    last_wifi = 0.0

    from pcap_check import pcap_help, pcap_ok

    print(f"[agent] Başlatıldı -> {base}")
    if MODEM_ENABLED:
        print("[agent] Modem modu açık (EV_AGI_MODEM_USER / EV_AGI_MODEM_PASS)")
    if not pcap_ok():
        print(f"[agent] UYARI:\n{pcap_help()}")

    print("[agent] İlk gönderim…")
    send_devices(base, monitor)
    send_modem(base)
    send_wifi(base)
    send_traffic(base, monitor)
    last_scan = last_traffic = last_modem = last_wifi = time.time()

    try:
        while True:
            now = time.time()
            if now - last_scan >= SCAN_INTERVAL:
                send_devices(base, monitor)
                last_scan = now
            if MODEM_ENABLED and now - last_modem >= MODEM_INTERVAL:
                send_modem(base)
                last_modem = now
            if now - last_wifi >= WIFI_INTERVAL:
                send_wifi(base)
                last_wifi = now
            if now - last_traffic >= TRAFFIC_REPORT_INTERVAL:
                send_traffic(base, monitor)
                last_traffic = now
            time.sleep(5)
    except KeyboardInterrupt:
        print("[agent] Durduruluyor...")
    finally:
        monitor.stop()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Ev ağı takip agent")
    p.add_argument("--server", default=DEFAULT_SERVER, help="Flask sunucu URL")
    p.add_argument("--iface", default=None, help="Sniff arayüzü")
    args = p.parse_args()
    run(server=args.server, interface=args.iface)
