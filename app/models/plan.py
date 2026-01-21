from sqlalchemy import String, Enum, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)

    # A stable identifier like: "one_time_basic", "recurring_monthly", "recurring_annual"
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    name = mapped_column(String(120))

    # One of: "one_time", "recurring"
    kind: Mapped[str] = mapped_column(
        Enum("one_time", "recurring", name="plan_kind")
    )

    # Money (use Numeric for currency)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="MXN")

    # For one_time plans: duration days of access
    # For recurring: we dont rely on this, but it can be informational
    access_duration_days : Mapped[int | None] = mapped_column(Integer, nullable=True)