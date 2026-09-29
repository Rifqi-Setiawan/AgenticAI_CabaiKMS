from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Variety(Base):
    __tablename__ = 'varieties'
    __table_args__ = {'schema': 'kms'}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    canonical_name: Mapped[str] = mapped_column(Text, unique=True)
    origin_region: Mapped[str | None] = mapped_column(Text)
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    metadata_json: Mapped[dict[str, Any]] = mapped_column('metadata', JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))


class Characteristic(Base):
    __tablename__ = 'characteristics'
    __table_args__ = {'schema': 'kms'}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    canonical_key: Mapped[str] = mapped_column(Text, unique=True)
    label_id: Mapped[str] = mapped_column(Text)
    organ_domain: Mapped[str | None] = mapped_column(Text)
    source_domain: Mapped[str] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(Text)
    standard_unit: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)


class AcquisitionRun(Base):
    __tablename__ = 'acquisition_runs'
    __table_args__ = {'schema': 'kms'}
    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_filename: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64))
    source_uri: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)
    template_hash: Mapped[str] = mapped_column(String(64))
    config_fingerprint: Mapped[str] = mapped_column(Text)
    total_attributes: Mapped[int] = mapped_column(Integer)
    auto_accepted_count: Mapped[int] = mapped_column(Integer)
    reviewed_count: Mapped[int] = mapped_column(Integer)
    execution_duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    status: Mapped[str] = mapped_column(Text, server_default=text("'STAGED'"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    draft_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    base_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    receipt: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CharacterValue(Base):
    __tablename__ = 'variety_character_values'
    __table_args__ = (UniqueConstraint('variety_id', 'characteristic_id'), {'schema': 'kms'})
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    variety_id: Mapped[UUID] = mapped_column(ForeignKey('kms.varieties.id'))
    characteristic_id: Mapped[UUID] = mapped_column(ForeignKey('kms.characteristics.id'))
    normalized_value: Mapped[Any] = mapped_column(JSONB)
    raw_source_value: Mapped[Any] = mapped_column(JSONB)
    value_type: Mapped[str] = mapped_column(Text)
    is_multi_value: Mapped[bool] = mapped_column(Boolean)
    confidence_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(ForeignKey('kms.acquisition_runs.run_id'))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))


class PlantImage(Base):
    __tablename__ = 'plant_images'
    __table_args__ = (UniqueConstraint('run_id', 'variety_id', 'organ_part', 'asset_id'), {'schema': 'kms'})
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    run_id: Mapped[str] = mapped_column(ForeignKey('kms.acquisition_runs.run_id'))
    variety_id: Mapped[UUID] = mapped_column(ForeignKey('kms.varieties.id'))
    organ_part: Mapped[str] = mapped_column(Text)
    asset_id: Mapped[str] = mapped_column(Text)
    vision_confidence: Mapped[float] = mapped_column(Float)
    vision_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
