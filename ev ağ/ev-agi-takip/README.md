# Ev Ağı Takip (ev-agi-takip)

Ev ağınızdaki cihazları tarayan ve veri kullanımını ölçen agent + Flask sunucu + web paneli.

## Klasör yapısı

```
ev-agi-takip/
├── agent/           # Evdeki PC (Scapy tarama + trafik)
├── server/          # Flask API + veritabanı
└── web_interface/   # HTML, CSS, JS
```

## Kurulum

PowerShell (klasör adında boşluk var — tırnak şart):

```powershell
cd "C:\Users\metin\Desktop\ev ağ\ev-agi-takip"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Kısayol scriptleri (tırnak sorunu yok):

```powershell
cd "C:\Users\metin\Desktop\ev ağ\ev-agi-takip"
.\run-server.ps1    # sunucu
.\run-agent.ps1     # agent
```

**Not:** Scapy ve paket dinleme Windows’ta **Yönetici** olarak çalıştırma ve Npcap kurulumu gerektirir.

## Çalıştırma

### 1. Sunucu (yerel veya PythonAnywhere)

```powershell
cd "C:\Users\metin\Desktop\ev ağ\ev-agi-takip"
$env:FLASK_SECRET_KEY = "uzun-gizli-anahtar"
$env:EV_AGI_AGENT_TOKEN = "agent-gizli-token"
.\run-server.ps1
```

Tarayıcı: http://127.0.0.1:5000 — demo giriş: `admin` / `admin`

### 2. Agent (evdeki bilgisayar)

```powershell
cd "C:\Users\metin\Desktop\ev ağ\ev-agi-takip"
$env:EV_AGI_SERVER = "http://127.0.0.1:5000"
$env:EV_AGI_AGENT_TOKEN = "agent-gizli-token"
.\run-agent.ps1
```

### 3. Modemden veri (tüm ev cihazları)

1. `modem.env.example` dosyasını `modem.env` olarak kopyalayın.
2. Modem admin şifresini yazın (kutunun arkası — Wi‑Fi şifresi olmayabilir).
3. Agent’ı yeniden başlatın.

```powershell
copy modem.env.example modem.env
# modem.env içinde EV_AGI_MODEM_PASS düzenleyin
.\run-agent.ps1
```

Terminalde `[modem] X cihaz alındı` görürseniz çalışıyordur. Panelde **Modem bağlı** yazar.

| Değişken | Açıklama |
|----------|----------|
| `EV_AGI_MODEM_URL` | `http://192.168.1.1` (boşsa otomatik ağ geçidi) |
| `EV_AGI_MODEM_USER` / `EV_AGI_MODEM_PASS` | Modem arayüzü girişi |
| `EV_AGI_MODEM_TYPE` | `auto`, `zte`, `huawei`, `tplink`, `openwrt`, `generic` |
| `EV_AGI_MODEM_INTERVAL` | Modem sorgu aralığı (sn), varsayılan 120 |

Tek seferlik tarama testi:

```powershell
cd "C:\Users\metin\Desktop\ev ağ\ev-agi-takip\agent"
..\.venv\Scripts\python.exe scanner.py
```

**Yanlış:** `cd "ev ağ"` sonra `python agent/agent_main.py` — dosya `ev-agi-takip\agent\` altında.

## Ortam değişkenleri

| Değişken | Açıklama |
|----------|----------|
| `EV_AGI_SERVER` | Agent’ın veri göndereceği sunucu URL |
| `EV_AGI_AGENT_TOKEN` | Agent ↔ sunucu paylaşımlı token |
| `EV_AGI_SCAN_INTERVAL` | Cihaz tarama aralığı (sn), varsayılan 300 |
| `EV_AGI_TRAFFIC_INTERVAL` | PC trafik raporu aralığı (sn), varsayılan 60 |
| `EV_AGI_MODEM_*` | Modem arayüzünden cihaz/trafik (bkz. yukarı) |
| `DATABASE_URL` | SQLAlchemy bağlantı dizesi (varsayılan SQLite) |
| `FLASK_SECRET_KEY` | Oturum şifreleme anahtarı |

## Özellikler (A+B+C)

| Kod | Özellik |
|-----|---------|
| **A** | HGW modem API (`hgw_modem.py`) — ev cihazları + GB |
| **B** | Panel: cihaz ismi, bugünkü GB, uyarı eşiği |
| **C** | Wi-Fi tarama (`netsh`) — ME30 / komşu SSID listesi |

## PythonAnywhere

- `server/` dosyalarını yükleyin; WSGI uygulamasını `app:app` olarak ayarlayın.
- `web_interface` klasörünü `server` ile aynı hiyerarşide tutun (mevcut `app.py` yolları buna göre).
- Agent’ı evde çalıştırıp `EV_AGI_SERVER` değerini PythonAnywhere URL’nize verin.
