"""
Kullanıcı ve cihaz veritabanı modelleri.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    devices = relationship("Device", back_populates="owner", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ip = Column(String(45), nullable=False, index=True)
    mac = Column(String(17), nullable=False, index=True)
    hostname = Column(String(255), default="")
    label = Column(String(120), default="")  # kullanıcı takma adı
    last_seen = Column(DateTime, default=datetime.utcnow)
    total_bytes = Column(Integer, default=0)

    owner = relationship("User", back_populates="devices")
    traffic_logs = relationship("TrafficLog", back_populates="device", cascade="all, delete-orphan")


class TrafficLog(Base):
    __tablename__ = "traffic_logs"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    ip = Column(String(45), nullable=False)
    bytes_delta = Column(Integer, default=0)
    gb_total = Column(Float, default=0.0)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)

    device = relationship("Device", back_populates="traffic_logs")


class AgentReport(Base):
    """Ham agent raporları (isteğe bağlı arşiv)."""
    __tablename__ = "agent_reports"

    id = Column(Integer, primary_key=True)
    report_type = Column(String(32))  # devices | traffic | modem | wifi
    payload = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class WifiNetwork(Base):
    """Çevredeki Wi-Fi ağları (netsh taraması)."""
    __tablename__ = "wifi_networks"

    id = Column(Integer, primary_key=True)
    ssid = Column(String(128), nullable=False, index=True)
    bssid = Column(String(17), default="")
    signal = Column(Integer, default=0)
    channel = Column(String(16), default="")
    security = Column(String(64), default="")
    band = Column(String(32), default="")
    likely_extender = Column(Integer, default=0)
    scanned_at = Column(DateTime, default=datetime.utcnow, index=True)


class AppSetting(Base):
    """Panel ayarları (uyarı eşiği vb.)."""
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(String(256), default="")
