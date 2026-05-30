"""
Modem / router arayüzünden bağlı cihaz ve (varsa) trafik verisi çeker.

Ortam değişkenleri:
  EV_AGI_MODEM_URL      örn. http://192.168.1.1
  EV_AGI_MODEM_USER     modem admin kullanıcı adı
  EV_AGI_MODEM_PASS     modem admin şifresi
  EV_AGI_MODEM_TYPE     auto | generic | zte | huawei | tplink | openwrt
"""

from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

import requests

MODEM_URL = os.environ.get("EV_AGI_MODEM_URL", "").strip()
MODEM_USER = os.environ.get("EV_AGI_MODEM_USER", "").strip()
MODEM_PASS = os.environ.get("EV_AGI_MODEM_PASS", "").strip()
MODEM_TYPE = os.environ.get("EV_AGI_MODEM_TYPE", "auto").strip().lower()
MODEM_ENABLED = os.environ.get("EV_AGI_MODEM_ENABLED", "1").strip() not in ("0", "false", "no")
MODEM_DEBUG = os.environ.get("EV_AGI_MODEM_DEBUG", "").strip() in ("1", "true", "yes")
PLACEHOLDER_PASS = ("buraya-modem-sifresi", "sifreniz", "password", "")

MAC_RE = re.compile(
    r"([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})"
)
IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")


@dataclass
class ModemDevice:
    ip: str
    mac: str
    hostname: str = ""
    bytes_total: int = 0
    bytes_rx: int = 0  # Okuma (Download)
    bytes_tx: int = 0  # Yazma (Upload)
    online: bool = True


def _normalize_mac(mac: str) -> str:
    m = MAC_RE.search(mac)
    if not m:
        return mac.lower()
    parts = re.split(r"[-:]", m.group(1))
    return ":".join(p.zfill(2) for p in parts)


def _is_lan_ip(ip: str) -> bool:
    if not IP_RE.fullmatch(ip):
        return False
    parts = [int(x) for x in ip.split(".")]
    if parts[0] == 10:
        return True
    if parts[0] == 192 and parts[1] == 168:
        return True
    if parts[0] == 172 and 16 <= parts[1] <= 31:
        return True
    return False


def get_default_gateway() -> Optional[str]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        local = s.getsockname()[0]
        s.close()
        parts = local.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3] + ["1"])
    except OSError:
        pass
    return None


def _int_bytes(val: Any) -> int:
    if val is None:
        return 0
    try:
        n = int(val)
        return max(0, n)
    except (TypeError, ValueError):
        return 0


def _pick(d: Dict[str, Any], *keys: str) -> Any:
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in lower:
            return lower[k.lower()]
    return None


def _extract_from_dict(d: Dict[str, Any], out: List[ModemDevice], seen: Set[str]) -> None:
    mac_raw = _pick(d, "mac", "macaddr", "macaddress", "hwaddr", "physaddress")
    ip_raw = _pick(d, "ip", "ipaddr", "ipaddress", "ipv4", "address")
    if not mac_raw and not ip_raw:
        return
    mac = _normalize_mac(str(mac_raw)) if mac_raw else ""
    ip = str(ip_raw).strip() if ip_raw else ""
    if mac and mac in seen:
        return
    if ip and not _is_lan_ip(ip):
        return
    if not mac and not ip:
        return
    if mac:
        seen.add(mac)
    hostname = str(_pick(d, "hostname", "name", "host", "devicename", "devicename") or "")
    rx = _int_bytes(_pick(d, "rxbytes", "rx_bytes", "bytesreceived", "download", "down"))
    tx = _int_bytes(_pick(d, "txbytes", "tx_bytes", "bytessent", "upload", "up"))
    total = _int_bytes(_pick(d, "bytestotal", "totalbytes", "traffic", "bytes"))
    if total == 0 and (rx or tx):
        total = rx + tx
    out.append(
        ModemDevice(
            ip=ip or "0.0.0.0",
            mac=mac or f"unknown:{ip}",
            hostname=hostname,
            bytes_total=total,
            bytes_rx=rx,
            bytes_tx=tx,
            online=bool(_pick(d, "online", "active", "connected") in (None, True, 1, "1", "true", "yes")),
        )
    )


def _walk_json(obj: Any, out: List[ModemDevice], seen: Set[str]) -> None:
    if isinstance(obj, dict):
        keys = {str(k).lower() for k in obj}
        if ("mac" in keys or "macaddr" in keys) and ("ip" in keys or "ipaddr" in keys):
            _extract_from_dict(obj, out, seen)
        for v in obj.values():
            _walk_json(v, out, seen)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json(item, out, seen)


def _parse_html_clients(html: str) -> List[ModemDevice]:
    out: List[ModemDevice] = []
    seen: Set[str] = set()
    for ip, mac in re.findall(
        r"(\d{1,3}(?:\.\d{1,3}){3})[\s\S]{0,120}?"
        r"([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})",
        html,
        re.I,
    ):
        if not _is_lan_ip(ip):
            continue
        mac_n = _normalize_mac(mac)
        if mac_n in seen:
            continue
        seen.add(mac_n)
        out.append(ModemDevice(ip=ip, mac=mac_n))
    return out


class ModemFetcher:
    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        modem_type: str = "auto",
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.modem_type = modem_type
        self.session = requests.Session()
        self.session.verify = False  # yerel modem HTTPS sertifikası
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EvAgiTakip/1.0",
                "Accept": "*/*",
                "Accept-Language": "tr-TR,tr;q=0.9",
            }
        )
        self._logged_in = False

    def _get(self, path: str) -> Optional[requests.Response]:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        try:
            r = self.session.get(url, timeout=12, allow_redirects=True)
            if MODEM_DEBUG:
                print(f"[modem] GET {path} -> {r.status_code} ({len(r.text)} byte)")
            return r
        except requests.RequestException as e:
            if MODEM_DEBUG:
                print(f"[modem] GET {path} hata: {e}")
            return None

    def _login(self) -> bool:
        if not self.username:
            return True

        # Önce ana sayfa (ZTE/Huawei gizli token alanları)
        home = self._get("/") or self._get("/index.asp")
        extra: Dict[str, str] = {}
        if home and home.text:
            for name in ("Frm_Logintoken", "logintoken", "token", "_sessiontoken"):
                m = re.search(
                    rf'name=["\']?{name}["\']?[^>]*value=["\']([^"\']+)',
                    home.text,
                    re.I,
                )
                if m:
                    extra[name] = m.group(1)

        login_paths = [
            "/login.cgi",
            "/login.asp",
            "/cgi-bin/luci/admin/login",
            "/",
            "/index.asp",
        ]
        payloads = [
            {"Username": self.username, "Password": self.password},
            {"username": self.username, "password": self.password},
            {"user": self.username, "pass": self.password},
            {"pwd": self.password, "username": self.username},
            {"Password": self.password, "Username": self.username},
            {"UserName": self.username, "PassWord": self.password},
        ]
        for path in login_paths:
            url = urljoin(self.base_url + "/", path.lstrip("/"))
            for data in payloads:
                merged = {**data, **extra}
                try:
                    r = self.session.post(
                        url, data=merged, timeout=12, allow_redirects=True
                    )
                    if MODEM_DEBUG:
                        print(f"[modem] POST {path} -> {r.status_code}")
                    if r.status_code < 500 and "login" not in r.url.lower():
                        self._logged_in = True
                        return True
                    if r.status_code < 500 and len(r.text) > 200:
                        self._logged_in = True
                        return True
                except requests.RequestException:
                    continue
        return False

    def _candidate_urls(self) -> List[str]:
        common = [
            "/get.json?modules=lanhosts:lanhosts",
            "/api/system/HostInfo",
            "/goform/getOnlineDevice",
            "/cgi-bin/luci/admin/status/overview?status=1",
            "/html/device/list",
            "/wlan_client_info.asp",
            "/gethostlist.cgi",
            "/InternetStatus.htm",
            "/status.htm",
            "/",
        ]
        by_type = {
            "hgw": [
                "/get_getlanhostlist.cgi",
                "/get_getnetworkconf.cgi",
                "/goform/getOnlineDevice",
                "/wlan_client_info.asp",
                "/gethostlist.cgi",
            ],
            "zte": [
                "/get_getlanhostlist.cgi",
                "/get_getnetworkconf.cgi",
                "/gethostlist.cgi",
                "/wlan_client_info.asp",
                "/goform/getOnlineDevice",
            ],
            "huawei": ["/api/system/HostInfo", "/html/device/list"],
            "tplink": ["/cgi-bin/luci/;stok=/locale?form=status"],
            "openwrt": ["/cgi-bin/luci/admin/status/overview?status=1"],
            "generic": common,
        }
        if self.modem_type == "auto":
            urls = []
            for key in ("hgw", "zte", "huawei", "tplink", "openwrt", "generic"):
                urls.extend(by_type.get(key, []))
            urls.extend(common)
        else:
            urls = by_type.get(self.modem_type, common)
        seen = set()
        ordered = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
        return ordered

    def fetch(self) -> Tuple[List[ModemDevice], str]:
        """Cihaz listesi ve kullanılan yöntem açıklaması."""
        if not self._logged_in:
            self._login()

        devices: List[ModemDevice] = []
        seen: Set[str] = set()
        method = "none"

        for path in self._candidate_urls():
            r = self._get(path)
            if not r or r.status_code >= 400:
                continue

            ctype = (r.headers.get("Content-Type") or "").lower()
            batch: List[ModemDevice] = []
            if "json" in ctype or r.text.strip().startswith(("{", "[")):
                try:
                    data = r.json()
                    _walk_json(data, batch, set())
                except json.JSONDecodeError:
                    pass
            if not batch and r.text:
                batch = _parse_html_clients(r.text)

            if batch:
                for d in batch:
                    if d.mac not in seen:
                        seen.add(d.mac)
                        devices.append(d)
                method = path
                if devices:
                    break

        return devices, method


_prev_modem_bytes: Dict[str, int] = {}


def modem_usage_deltas(devices: List[ModemDevice]) -> List[dict]:
    """Kümülatif modem sayaçlarından delta üretir."""
    global _prev_modem_bytes
    usage = []
    for d in devices:
        if d.bytes_total <= 0:
            continue
        prev = _prev_modem_bytes.get(d.mac, 0)
        delta = d.bytes_total - prev if d.bytes_total >= prev else d.bytes_total
        _prev_modem_bytes[d.mac] = d.bytes_total
        if delta > 0:
            usage.append(
                {
                    "ip": d.ip,
                    "mac": d.mac,
                    "bytes_delta": delta,
                    "bytes": delta,
                    "gb": round(delta / (1024**3), 4),
                    "is_local_pc": False,
                    "source": "modem",
                }
            )
    return usage


def _modem_pass_ok() -> bool:
    if not MODEM_PASS or MODEM_PASS in PLACEHOLDER_PASS:
        return False
    if "buraya" in MODEM_PASS.lower():
        return False
    return True


def fetch_modem_devices() -> Tuple[List[ModemDevice], str]:
    if not MODEM_ENABLED:
        return [], "disabled"
    if not MODEM_USER or not _modem_pass_ok():
        print(
            "[modem] modem.env -> EV_AGI_MODEM_PASS alanına gerçek modem şifresini yazın "
            "(kutunun arkası, Wi‑Fi şifresi değil)"
        )
        return [], "no_credentials"

    bases: List[str] = []
    if MODEM_URL:
        bases.append(MODEM_URL.rstrip("/"))
        if MODEM_URL.startswith("http://"):
            bases.append("https://" + MODEM_URL[7:].rstrip("/"))
    gw = get_default_gateway()
    if gw:
        bases.extend([f"http://{gw}", f"https://{gw}"])
    seen_b = set()
    unique_bases = []
    for b in bases:
        if b not in seen_b:
            seen_b.add(b)
            unique_bases.append(b)

    if not unique_bases:
        print("[modem] EV_AGI_MODEM_URL veya ağ geçidi bulunamadı")
        return [], "no_url"

    # urllib3 uyarılarını kapat (yerel modem)
    try:
        import urllib3

        urllib3.disable_warnings()
    except ImportError:
        pass

    for base in unique_bases:
        print(f"[modem] Deneniyor: {base} (tip={MODEM_TYPE})")
        if MODEM_TYPE in ("hgw", "zte", "auto"):
            try:
                from hgw_modem import fetch_hgw

                sess = requests.Session()
                sess.verify = False
                hgw_dev = fetch_hgw(sess, base, MODEM_USER, MODEM_PASS)
                if hgw_dev:
                    print(f"[modem] HGW API: {len(hgw_dev)} cihaz")
                    return hgw_dev, "/get_getlanhostlist.cgi"
            except Exception as e:
                if MODEM_DEBUG:
                    print(f"[modem] HGW denemesi: {e}")

        fetcher = ModemFetcher(base, MODEM_USER, MODEM_PASS, MODEM_TYPE)
        try:
            devices, method = fetcher.fetch()
            if devices:
                print(f"[modem] {len(devices)} cihaz alindi ({base}{method})")
                return devices, method
        except requests.RequestException as e:
            print(f"[modem] {base} hata: {e}")
            continue

    print(
        "[modem] Cihaz alınamadı. Deneyin:\n"
        "  1) Tarayıcıda 192.168.1.1 açılıyor mu? Şifre doğru mu?\n"
        "  2) modem.env -> EV_AGI_MODEM_TYPE=zte (veya huawei)\n"
        "  3) .\\test-modem.ps1 ile test"
    )
    return [], "error"


def modem_devices_to_dict(devices: List[ModemDevice]) -> List[dict]:
    return [
        {
            "ip": d.ip,
            "mac": d.mac,
            "hostname": d.hostname,
            "bytes_total": d.bytes_total,
            "source": "modem",
        }
        for d in devices
    ]
