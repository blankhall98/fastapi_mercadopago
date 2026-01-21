from datetime import datetime
from sqlalchemy import ForeignKey, Enum, DateTime, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Entitlement(Base):
    __tablename__ = "entitlements"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)

    # Status = our internal truth for gating
    status: Mapped[str] = mapped_column(
        Enum("inactive","active","past_due","canceled", name = "entitlement_status"),
        default="inactive",
        index=True
    )

    # For one-time purchases, when does access expire
    # For recurring: optional
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Mercado Pago Preferences (nullable because not all apply)
    mp_preference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mp_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mp_preapproval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    updated_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    plan = relationship("Plan")

    __table_args__ = (
        UniqueConstraint('user_id', 'plan_id', name='uq_entitlements_user_plan'),
        Index("ix_entitlements_user_status","user_id","status")
    )