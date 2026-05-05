"""SQLAlchemy ORM models."""
from __future__ import annotations

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class VesselSnapshot(Base):
    __tablename__ = "vessels_snapshot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_month = Column(String(7), nullable=False, index=True)
    vessel_key = Column(String(255), nullable=False, index=True)
    search_code = Column(String(16), index=True)
    nama_kapal = Column(String(255))
    eks_nama_kapal = Column(String(255))
    call_sign = Column(String(64), index=True)
    jenis_kapal = Column(String(255))
    nama_pemilik = Column(String(255))
    tpk = Column(String(255))
    panjang = Column(Float)
    lebar = Column(Float)
    dalam = Column(Float)
    length_of_all = Column(Float)
    gt = Column(Float)
    isi_bersih = Column(Float)
    imo = Column(String(64))
    tahun = Column(String(16))
    raw_data = Column(Text)
    content_hash = Column(String(64), index=True)
    scraped_at = Column(DateTime)
    __table_args__ = (
        UniqueConstraint("snapshot_month", "vessel_key", name="uq_vessel_snapshot_month_key"),
    )


class VesselCurrent(Base):
    __tablename__ = "vessels_current"
    vessel_key = Column(String(255), primary_key=True)
    snapshot_month_latest = Column(String(7))
    nama_kapal = Column(String(255))
    call_sign = Column(String(64), index=True)
    jenis_kapal = Column(String(255))
    nama_pemilik = Column(String(255))
    gt = Column(Float)
    tahun = Column(String(16))
    panjang = Column(Float)
    lebar = Column(Float)
    dalam = Column(Float)
    imo = Column(String(64))
    first_seen_month = Column(String(7))
    last_seen_month = Column(String(7))
    status = Column(String(16), default="active")


class VesselChange(Base):
    __tablename__ = "vessels_changes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    change_month = Column(String(7), nullable=False, index=True)
    vessel_key = Column(String(255), nullable=False, index=True)
    change_type = Column(String(16), nullable=False)  # ADDED/REMOVED/MODIFIED
    field_name = Column(String(64))
    old_value = Column(Text)
    new_value = Column(Text)
    detected_at = Column(DateTime)


class Port(Base):
    __tablename__ = "ports"
    kode_pelabuhan = Column(String(32), primary_key=True)
    nama_pelabuhan = Column(String(255))
    last_seen = Column(DateTime)


class CargoSnapshot(Base):
    __tablename__ = "cargo_snapshot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_month = Column(String(7), nullable=False, index=True)
    kode_pelabuhan = Column(String(32), nullable=False, index=True)
    data_year = Column(Integer, nullable=False, index=True)
    data_month = Column(Integer, nullable=False, index=True)
    kind = Column(String(8), nullable=False, index=True)  # dn/ln
    row_index = Column(Integer, nullable=False)
    raw_row = Column(Text)
    row_hash = Column(String(64), index=True)
    scraped_at = Column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "snapshot_month", "kode_pelabuhan", "data_year", "data_month", "kind", "row_index",
            name="uq_cargo_snapshot",
        ),
        Index("ix_cargo_lookup", "kode_pelabuhan", "data_year", "data_month", "kind"),
    )


class CargoMonthlySummary(Base):
    __tablename__ = "cargo_monthly_summary"
    kode_pelabuhan = Column(String(32), primary_key=True)
    data_year = Column(Integer, primary_key=True)
    data_month = Column(Integer, primary_key=True)
    kind = Column(String(8), primary_key=True)
    vessel_calls = Column(Integer, default=0)
    total_cargo_ton = Column(Float, default=0.0)
    container_teu = Column(Float, default=0.0)
    extra_metrics = Column(Text)
    last_updated_snapshot = Column(String(7))


class CargoChange(Base):
    __tablename__ = "cargo_changes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    change_month = Column(String(7), nullable=False, index=True)
    kode_pelabuhan = Column(String(32), nullable=False, index=True)
    data_year = Column(Integer, nullable=False)
    data_month = Column(Integer, nullable=False)
    kind = Column(String(8), nullable=False)
    change_type = Column(String(16), nullable=False)  # ADDED/REMOVED/REVISED
    field_name = Column(String(64))
    old_value = Column(Text)
    new_value = Column(Text)
    delta = Column(Float)
    delta_pct = Column(Float)
    detected_at = Column(DateTime)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_month = Column(String(7), nullable=False, index=True)
    task = Column(String(32), nullable=False)  # fleet/cargo/diff/report
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    status = Column(String(16))  # success/partial/failed/running
    total_targets = Column(Integer)
    succeeded = Column(Integer)
    failed = Column(Integer)
    notes = Column(Text)
