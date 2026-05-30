"""
Ağdaki cihazları ARP taraması ile bulur.
Ev ağındaki agent bilgisayarda çalışır; yönetici (root/admin) gerekebilir.
"""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import List, Optional

try:
    from scapy.all import ARP, Ether, srp  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


@dataclass
class Device:
    ip: str
    mac: str
    hostname: Optional[str] = None


def _local_subnet() -> str:
    """Varsayılan ağ arayüzünden /24 alt ağ tahmini."""
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    return str(network)


def _resolve_hostname(ip: str) -> Optional[str]:
    try:
        name, _, _ = socket.gethostbyaddr(ip)
        return name
    except (socket.herror, socket.gaierror, OSError):
        return None


def _normalize_mac(mac: str) -> str:
    m = mac.replace("-", ":").lower()
    parts = m.split(":")
    if len(parts) == 6:
        return ":".join(p.zfill(2) for p in parts)
    return mac.lower()


def scan_arp_table() -> List[Device]:
    """Npcap olmadan Windows ARP tablosundan cihaz listesi (sınırlı)."""
    if platform.system() != "Windows":
        return []
    try:
        out = subprocess.check_output(
            ["arp", "-a"],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[scanner] arp -a hatası: {e}")
        return []

    seen = set()
    devices: List[Device] = []
    row = re.compile(
        r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})"
    )
    for ip, mac in row.findall(out):
        if ip.startswith("224.") or ip.endswith(".255"):
            continue
        mac = _normalize_mac(mac)
        if mac in seen:
            continue
        seen.add(mac)
        devices.append(Device(ip=ip, mac=mac, hostname=_resolve_hostname(ip)))

    if devices:
        print(f"[scanner] ARP tablosundan {len(devices)} cihaz (Npcap taraması değil)")
    return devices


def _scan_scapy(subnet: Optional[str], timeout: int) -> List[Device]:
    if not SCAPY_AVAILABLE:
        return []

    from pcap_check import pcap_ok

    if not pcap_ok():
        return []

    target = subnet or _local_subnet()
    arp = ARP(pdst=target)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether / arp

    try:
        answered, _ = srp(packet, timeout=timeout, verbose=0)
    except RuntimeError as e:
        if "winpcap" in str(e).lower() or "npcap" in str(e).lower():
            return []
        raise
    devices: List[Device] = []

    for _, received in answered:
        ip = received.psrc
        mac = _normalize_mac(received.hwsrc)
        devices.append(
            Device(ip=ip, mac=mac, hostname=_resolve_hostname(ip))
        )

    return devices


def scan_network(subnet: Optional[str] = None, timeout: int = 2) -> List[Device]:
    """
    Önce Scapy ARP taraması; olmazsa Windows arp tablosu.
    """
    devices: List[Device] = []
    try:
        devices = _scan_scapy(subnet, timeout)
    except RuntimeError as e:
        if "winpcap" in str(e).lower() or "npcap" in str(e).lower():
            from pcap_check import pcap_help

            print(f"[scanner] Scapy kullanılamıyor, ARP tablosu deneniyor…")
            print(f"[scanner] Tam tarama için: {pcap_help()}")
        else:
            raise

    if not devices:
        devices = scan_arp_table()

    return devices


def devices_to_dict(devices: List[Device]) -> List[dict]:
    return [
        {"ip": d.ip, "mac": d.mac, "hostname": d.hostname or ""}
        for d in devices
    ]


if __name__ == "__main__":
    for dev in scan_network():
        label = dev.hostname or "?"
        print(f"{dev.ip:15} {dev.mac:17} {label}")
