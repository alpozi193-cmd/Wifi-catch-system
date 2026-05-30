"""Windows'ta Npcap / WinPcap kontrolü."""

from __future__ import annotations


def pcap_ok() -> bool:
    try:
        from scapy.arch.windows import get_windows_if_list  # type: ignore

        get_windows_if_list()
        return True
    except Exception:
        return False


def pcap_help() -> str:
    return (
        "Npcap gerekli (https://npcap.com/).\n"
        "  1) Npcap kur -> 'WinPcap API-compatible Mode' işaretli olsun\n"
        "  2) Bilgisayarı yeniden başlat (veya en azından terminali kapat-aç)\n"
        "  3) PowerShell'i Yönetici olarak aç -> run-agent.ps1"
    )
