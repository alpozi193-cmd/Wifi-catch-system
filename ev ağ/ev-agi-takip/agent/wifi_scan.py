"""
Windows: çevredeki Wi-Fi ağlarını listeler (ME30 / modem SSID dahil).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class WifiNetwork:
    ssid: str
    bssid: str
    signal: int
    channel: str
    security: str
    band: str = ""
    likely_extender: bool = False


EXTENDER_HINTS = ("me30", "miwifi", "xiaomi", "repeater", "extender", "çoğalt", "cogalt")


def _guess_extender(ssid: str) -> bool:
    s = ssid.lower()
    return any(h in s for h in EXTENDER_HINTS)


def scan_wifi_networks() -> List[WifiNetwork]:
    """netsh wlan show networks mode=Bssid"""
    try:
        out = subprocess.check_output(
            ["netsh", "wlan", "show", "networks", "mode=Bssid"],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
        )
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[wifi] Tarama hatasi: {e}")
        return []

    networks: List[WifiNetwork] = []
    current_ssid = ""
    current: dict = {}

    for line in out.splitlines():
        line = line.strip()
        if line.startswith("SSID") and ":" in line and "BSSID" not in line:
            if current_ssid and current.get("bssid"):
                networks.append(_row(current_ssid, current))
            parts = line.split(":", 1)
            current_ssid = parts[1].strip() if len(parts) > 1 else ""
            current = {}
        elif current_ssid and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "bssid":
                if current.get("bssid"):
                    networks.append(_row(current_ssid, current))
                current = {"bssid": val.replace("-", ":").lower()}
            elif key in ("signal", "kanal", "channel"):
                if "signal" in key or key == "signal":
                    m = re.search(r"(\d+)", val)
                    current["signal"] = int(m.group(1)) if m else 0
                else:
                    current["channel"] = val
            elif "authentication" in key or "güvenlik" in key or "guvenlik" in key:
                current["security"] = val
            elif key in ("band", "radio type", "radyo türü"):
                current["band"] = val

    if current_ssid and current.get("bssid"):
        networks.append(_row(current_ssid, current))

    # SSID yok satirlari filtrele
    uniq = {}
    for n in networks:
        key = (n.ssid, n.bssid)
        if key not in uniq or n.signal > uniq[key].signal:
            uniq[key] = n
    result = list(uniq.values())
    if result:
        ext = sum(1 for n in result if n.likely_extender)
        print(f"[wifi] {len(result)} ag bulundu ({ext} olasi cogaltici)")
    return result


def _row(ssid: str, d: dict) -> WifiNetwork:
    ssid = ssid or "(gizli)"
    return WifiNetwork(
        ssid=ssid,
        bssid=d.get("bssid", ""),
        signal=int(d.get("signal", 0)),
        channel=str(d.get("channel", "")),
        security=d.get("security", ""),
        band=d.get("band", ""),
        likely_extender=_guess_extender(ssid),
    )


def wifi_to_dict(networks: List[WifiNetwork]) -> List[dict]:
    return [
        {
            "ssid": n.ssid,
            "bssid": n.bssid,
            "signal": n.signal,
            "channel": n.channel,
            "security": n.security,
            "band": n.band,
            "likely_extender": n.likely_extender,
        }
        for n in networks
    ]
