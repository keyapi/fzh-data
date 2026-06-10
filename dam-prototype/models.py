"""DAM 数据模型 — SQLAlchemy + SQLite (原型) / MariaDB (生产).

实体:
  Asset            — 数字资产 (图片/视频/文档)
  Tag              — 受控标签分类法
  AssetTag         — Asset-Tag 多对多关联
  AssetProductLink — Asset-ERPNext Item 产品关联
  AssetCollection  — 有序资产快照 (虚拟分组)
  AssetCollectionItem — Collection 中的资产条目 (position + role)
  AssetCollectionVersion — Collection 版本历史
  PlatformPreset   — 平台输出规格定义
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, DateTime, ForeignKey,
    Text, JSON, Enum, Table, UniqueConstraint, create_engine, Index, Float,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.orm import Session

# ── Base ──────────────────────────────────────────────

class Base(DeclarativeBase):
    pass

# ── 多对多关联表 ─────────────────────────────────────

asset_tag_table = Table(
    "asset_tag", Base.metadata,
    Column("asset_id", String(36), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

# ── Asset ─────────────────────────────────────────────

class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # NAS 路径
    asset_type: Mapped[str] = mapped_column(String(20), default="image")    # image|video|document
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    thumbnail_path: Mapped[str] = mapped_column(String(1000), nullable=True)

    # 元数据
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)       # AI 原始响应

    # 业务属性 (对应 ERPNext 枚举值)
    style: Mapped[str | None] = mapped_column(String(200), nullable=True)       # Item Group.custom_model_id
    fabric: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size: Mapped[str | None] = mapped_column(String(200), nullable=True)
    color: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # 图片角色
    image_role: Mapped[str | None] = mapped_column(String(30), nullable=True)   # main|alternate|lifestyle|detail|size_chart|packaging|a_plus|other

    # AI 标签状态
    ai_tags_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # 合规
    compliance_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # pending|passed|failed|na
    compliance_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="draft")             # draft|pending_review|approved|rejected|archived
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id"), nullable=True)

    # 时间戳
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    uploaded_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关联
    tags: Mapped[list["Tag"]] = relationship(secondary=asset_tag_table, back_populates="assets", lazy="selectin")
    product_links: Mapped[list["AssetProductLink"]] = relationship(back_populates="asset", lazy="selectin")
    collection_items: Mapped[list["AssetCollectionItem"]] = relationship(back_populates="asset", lazy="selectin")

    __table_args__ = (
        Index("idx_asset_status", "status"),
        Index("idx_asset_hash", "content_hash"),
        Index("idx_asset_style", "style"),
        Index("idx_asset_type", "asset_type"),
    )


# ── Tag ───────────────────────────────────────────────

class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)      # color|angle|style|fabric|size|role|scene|season|custom
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    assets: Mapped[list["Asset"]] = relationship(secondary=asset_tag_table, back_populates="tags", lazy="selectin")


# ── AssetProductLink ──────────────────────────────────

class AssetProductLink(Base):
    __tablename__ = "asset_product_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    product_sku: Mapped[str] = mapped_column(String(200), nullable=False)        # ERPNext Item.item_code
    match_level: Mapped[str] = mapped_column(String(20), default="exact")        # exact|style|style_fabric|style_fabric_size
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    asset: Mapped["Asset"] = relationship(back_populates="product_links")

    __table_args__ = (
        Index("idx_apl_sku", "product_sku"),
        Index("idx_apl_asset", "asset_id"),
    )


# ── AssetCollection ───────────────────────────────────

class AssetCollection(Base):
    __tablename__ = "asset_collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="custom")              # listing|campaign|social_post|catalog|custom
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)             # 按 type 不同: {product_sku, channel} | {campaign_name, season} | ...
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")              # draft|active|archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    items: Mapped[list["AssetCollectionItem"]] = relationship(back_populates="collection", lazy="selectin",
        order_by="AssetCollectionItem.position")
    versions: Mapped[list["AssetCollectionVersion"]] = relationship(back_populates="collection", lazy="selectin")

    __table_args__ = (
        Index("idx_ac_type", "type"),
        Index("idx_ac_status", "status"),
    )


# ── AssetCollectionItem ──────────────────────────────

class AssetCollectionItem(Base):
    __tablename__ = "asset_collection_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id: Mapped[str] = mapped_column(String(36), ForeignKey("asset_collections.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)           # main|alternate|lifestyle|detail|size_chart|a_plus

    collection: Mapped["AssetCollection"] = relationship(back_populates="items")
    asset: Mapped["Asset"] = relationship(back_populates="collection_items")

    __table_args__ = (
        UniqueConstraint("collection_id", "position", name="uq_collection_position"),
    )


# ── AssetCollectionVersion ────────────────────────────

class AssetCollectionVersion(Base):
    __tablename__ = "asset_collection_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id: Mapped[str] = mapped_column(String(36), ForeignKey("asset_collections.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)                   # 完整 images 数组快照 [{asset_id, position, role}, ...]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    collection: Mapped["AssetCollection"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("collection_id", "version", name="uq_collection_version"),
    )


# ── PlatformPreset ────────────────────────────────────

class PlatformPreset(Base):
    __tablename__ = "platform_presets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)    # "amazon-main"
    label: Mapped[str] = mapped_column(String(200), nullable=False)               # "Amazon 主图"
    platform: Mapped[str] = mapped_column(String(30), nullable=False)              # amazon|wayfair|shopify|home24
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)            # main|alternate|a_plus
    width: Mapped[int] = mapped_column(Integer, default=2000)
    format: Mapped[str] = mapped_column(String(10), default="jpeg")
    quality: Mapped[int] = mapped_column(Integer, default=85)
    colorspace: Mapped[str] = mapped_column(String(20), default="sRGB")
    rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)                # {background, product_fill_pct, no_text, no_logo, ...}


# ── 工厂函数 ──────────────────────────────────────────

def init_db(db_url: str = "sqlite:///dam.db") -> Session:
    """初始化数据库并返回 session."""
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_presets(session: Session) -> None:
    """插入平台预设数据 (幂等)."""
    presets = [
        PlatformPreset(code="amazon-main", label="Amazon 主图", platform="amazon", role="main",
                       width=2000, format="jpeg", quality=90, colorspace="sRGB",
                       rules={"background": "pure_white", "product_fill_pct": 85, "no_text": True, "no_logo": True}),
        PlatformPreset(code="amazon-alt", label="Amazon 副图", platform="amazon", role="alternate",
                       width=2000, format="jpeg", quality=85, colorspace="sRGB", rules={}),
        PlatformPreset(code="wayfair-main", label="Wayfair 主图", platform="wayfair", role="main",
                       width=2000, format="jpeg", quality=90, colorspace="sRGB",
                       rules={"background": "pure_white", "product_fill_pct": 85, "no_text": True, "no_logo": True, "no_human": True}),
        PlatformPreset(code="shopify-main", label="Shopify 主图", platform="shopify", role="main",
                       width=2048, format="webp", quality=85, colorspace="sRGB", rules={}),
        PlatformPreset(code="home24-main", label="Home24 主图", platform="home24", role="main",
                       width=1000, format="jpeg", quality=85, colorspace="sRGB",
                       rules={"background": "white", "product_fill_pct": 85}),
    ]
    for p in presets:
        existing = session.query(PlatformPreset).filter_by(code=p.code).first()
        if not existing:
            session.add(p)
    session.commit()
