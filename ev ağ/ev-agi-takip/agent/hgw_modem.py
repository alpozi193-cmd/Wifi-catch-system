"""
Turk Telekom / Superonline HGW (ZTE) modem - LAN host listesi ve trafik.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import requests

    from modem_client import ModemDevice


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_lan_host_xml(text: str) -> List["ModemDevice"]:
    from modem_client import ModemDevice, _normalize_mac

    devices: List[ModemDevice] = []
    if not text or "<" not in text:
        return devices
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return devices

    for host in root.iter():
        tag = host.tag.split("}")[-1].lower()
        if tag not in ("host", "item", "client", "station"):
            continue
        ip = _text(host.find("IPAddress")) or _text(host.find("ip")) or _text(
            host.find("IpAddress")
        )
        mac = _text(host.find("MACAddress")) or _text(host.find("mac")) or _text(
            host.find("MacAddress")
        )
        if not mac:
            for k, v in host.attrib.items():
                if k.lower() in ("mac", "macaddress"):
                    mac = v
                if k.lower() in ("ip", "ipaddress"):
                    ip = ip or v
        if not mac and not ip:
            continue
        name = (
            _text(host.find("HostName"))
            or _text(host.find("hostname"))
            or _text(host.find("name"))
            or ""
        )
        rx = _parse_num(
            _text(host.find("BytesReceived"))
            or _text(host.find("RxBytes"))
            or host.attrib.get("BytesReceived", "")
        )
        tx = _parse_num(
            _text(host.find("BytesSent"))
            or _text(host.find("TxBytes"))
            or host.attrib.get("BytesSent", "")
        )
        total = rx + tx
        mac_n = _normalize_mac(mac) if mac else ""
        if not mac_n and not ip:
            continue
        devices.append(
            ModemDevice(
                ip=ip or "0.0.0.0",
                mac=mac_n or f"unknown:{ip}",
                hostname=name,
                bytes_total=total,
            )
        )
    return devices


def _parse_num(s: str) -> int:
    if not s:
        return 0
    try:
        return max(0, int(re.sub(r"[^\d]", "", str(s)) or "0"))
    except ValueError:
        return 0


def fetch_hgw(
    session: "requests.Session", base_url: str, username: str, password: str
) -> List["ModemDevice"]:
    from urllib.parse import urljoin

    from modem_client import ModemDevice, _parse_html_clients, _walk_json
    import json

    login_url = urljoin(base_url + "/", "login.cgi")
    try:
        # Session başlatmak için ana sayfaya git
        res = session.get(urljoin(base_url + "/", "/"), timeout=10)
        # Eğer modem token kullanıyorsa buradan regex ile çekilebilir.
        
        r = session.post(
            login_url,
            data={"Username": username, "Password": password},
            timeout=12,
        )
        if "login" in r.url.lower() or r.status_code >= 400:
             print(f"[modem] Giris basarisiz görünüyor. Status: {r.status_code}")
        else:
             print(f"[modem] Giris basarili: {base_url}")

    except Exception as e:
        print(f"[modem] Login hatasi: {e}")

    paths = [
        "/get_getlanhostlist.cgi",
        "/get_getnetworkconf.cgi?module=lanhosts",
        "/gethostlist.cgi",
        "/goform/getOnlineDevice",
    ]
    all_dev: List[ModemDevice] = []
    seen = set()

    for path in paths:
        url = urljoin(base_url + "/", path.lstrip("/"))
        try:
            r = session.get(url, timeout=12)
        except requests.RequestException as e:
            print(f"[modem] {path} sorgulanırken hata olustu: {e}")
            continue
        if r.status_code >= 400:
            continue
        batch: List[ModemDevice] = []
        text = r.text
        if "LANHost" in text or "<Host" in text or "<host" in text:
            batch = parse_lan_host_xml(text)
        elif text.strip().startswith(("{", "[")):
            try:
                data = json.loads(text)
                from modem_client import ModemDevice as MD

                tmp: List[MD] = []
                _walk_json(data, tmp, set())
                batch = tmp
            except json.JSONDecodeError:
                pass
        if not batch:
            batch = [
                ModemDevice(ip=d.ip, mac=d.mac, hostname=d.hostname)
                for d in _parse_html_clients(text)
            ]
        for d in batch:
            if d.mac not in seen:
                seen.add(d.mac)
                all_dev.append(d)
        if all_dev:
            break

    return all_dev
