"""Organization (company profile) master."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.mixins import AuditableBase
from app.models.mixins import NamedMasterMixin, status_check, unique_ci


class Organization(Base, AuditableBase, NamedMasterMixin):
    """The legal entity the platform is operated for.

    Modelled as a table rather than a settings blob so that a group operating
    several registered entities can be supported without a schema change. ``name``
    holds the trading/company name; ``legal_name`` holds the registered name.
    """

    __tablename__ = "organizations"
    __table_args__ = (
        unique_ci("uq_organizations_name_lower", "name"),
        unique_ci("uq_organizations_registration_number_lower", "registration_number"),
        status_check(),
        {"comment": "Legal entities the platform is operated for."},
    )

    # -- Registration -------------------------------------------------
    legal_name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        doc="Registered legal name, which often differs from the trading name.",
    )
    registration_number: Mapped[str] = mapped_column(String(100), nullable=False)
    gst_number: Mapped[str | None] = mapped_column(
        String(15), nullable=True, doc="Optional. 15-character Indian GSTIN."
    )
    pan_number: Mapped[str | None] = mapped_column(
        String(10), nullable=True, doc="Optional. 10-character Indian PAN."
    )

    # -- Presentation --------------------------------------------------
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # -- Localisation --------------------------------------------------
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="IANA timezone identifier, e.g. Asia/Kolkata."
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, doc="ISO 4217 alphabetic currency code, e.g. INR."
    )

    # -- Registered address --------------------------------------------
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name={self.name!r}>"
