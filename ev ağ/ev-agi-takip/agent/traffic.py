"""

Ağ trafiğini dinleyerek cihaz bazlı veri kullanımını (bayt) ölçer.



ÖNEMLİ: Ev Wi‑Fi'da bu PC yalnızca kendi ağ kartından geçen paketleri görür.

Telefon/tablet trafiği modem üzerinden gider; bu bilgisayardan görünmez.

"""



from __future__ import annotations



import ipaddress

import socket

import threading

from collections import defaultdict

from dataclasses import dataclass, field

from typing import Dict, List, Optional, Set



try:

    from scapy.all import IP, sniff  # type: ignore

    SCAPY_AVAILABLE = True

except ImportError:

    SCAPY_AVAILABLE = False





BYTES_PER_GB = 1024 ** 3





def get_local_ips() -> Set[str]:

    """Bu bilgisayarın yerel IP adresleri."""

    ips: Set[str] = set()

    try:

        ips.add(socket.gethostbyname(socket.gethostname()))

    except OSError:

        pass

    try:

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        s.settimeout(1)

        s.connect(("8.8.8.8", 80))

        ips.add(s.getsockname()[0])

        s.close()

    except OSError:

        pass

    return {ip for ip in ips if ip and not ip.startswith("127.")}





def _is_lan(ip: str) -> bool:

    try:

        return ipaddress.ip_address(ip).is_private

    except ValueError:

        return False





@dataclass

class TrafficStats:

    bytes_by_ip: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    _lock: threading.Lock = field(default_factory=threading.Lock)



    def add(self, ip: str, size: int) -> None:

        with self._lock:

            self.bytes_by_ip[ip] += size



    def pop_deltas(self) -> Dict[str, int]:

        """Son rapordan bu yana biriken baytları al ve sıfırla."""

        with self._lock:

            snap = dict(self.bytes_by_ip)

            self.bytes_by_ip.clear()

        return snap



    def total_bytes(self) -> int:

        with self._lock:

            return sum(self.bytes_by_ip.values())



    def total_gb(self) -> float:

        return self.total_bytes() / BYTES_PER_GB





class TrafficMonitor:

    """Arka planda paket koklar — görülen trafik bu PC ve nadiren LAN."""



    def __init__(

        self,

        interface: Optional[str] = None,

        local_ips: Optional[Set[str]] = None,

        known_ips: Optional[Set[str]] = None,

    ):

        self.interface = interface

        self.local_ips: Set[str] = local_ips or get_local_ips()

        self.known_ips: Set[str] = set(known_ips or [])

        self.stats = TrafficStats()

        self._stop = threading.Event()

        self._thread: Optional[threading.Thread] = None



    def set_known_ips(self, ips: Set[str]) -> None:

        self.known_ips = set(ips)



    def _owner_ip(self, src: str, dst: str) -> Optional[str]:

        """Yalnızca bu PC — telefon/TV trafiği modem API ile gelmeli."""

        if src in self.local_ips or dst in self.local_ips:

            return next(iter(self.local_ips), src)

        return None



    def _on_packet(self, packet) -> None:

        if not packet.haslayer(IP):

            return

        ip_layer = packet[IP]

        src, dst = ip_layer.src, ip_layer.dst

        owner = self._owner_ip(src, dst)

        if owner:

            self.stats.add(owner, len(packet))



    def _run(self) -> None:

        if not SCAPY_AVAILABLE:

            return

        from pcap_check import pcap_help, pcap_ok



        if not pcap_ok():

            print(f"[traffic] {pcap_help()}")

            return

        print(

            f"[traffic] Dinlenen PC IP: {', '.join(sorted(self.local_ips)) or '?'}"

        )

        print(

            "[traffic] Not: Wi‑Fi'da diğer telefonların interneti bu PC'den geçmez; "

            "sadece bu bilgisayarın trafiği ölçülür."

        )

        try:

            sniff(

                iface=self.interface,

                prn=self._on_packet,

                store=False,

                promisc=True,

                stop_filter=lambda _: self._stop.is_set(),

            )

        except RuntimeError as e:

            if "winpcap" in str(e).lower() or "npcap" in str(e).lower():

                print(f"[traffic] {pcap_help()}")

                return

            raise



    def start(self) -> None:

        if not SCAPY_AVAILABLE or self._thread:

            return

        self._stop.clear()

        self._thread = threading.Thread(target=self._run, daemon=True)

        self._thread.start()



    def stop(self) -> None:

        self._stop.set()

        if self._thread:

            self._thread.join(timeout=5)

            self._thread = None



    def usage_report(self) -> List[dict]:

        """Son aralıktaki artış (delta) — sunucuya gönderilir."""

        snap = self.stats.pop_deltas()

        return [

            {

                "ip": ip,

                "bytes_delta": nbytes,

                "bytes": nbytes,

                "gb": round(nbytes / BYTES_PER_GB, 4),

                "is_local_pc": ip in self.local_ips,

            }

            for ip, nbytes in sorted(snap.items(), key=lambda x: -x[1])

            if nbytes > 0

        ]


