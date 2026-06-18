"""Development seed data for service templates."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.database import db_manager
from app.core.security import generate_id
from app.modules.services.constants import COLOUR_HEX_MAP
from app.modules.services.models import (
    Service,
    ServiceDocumentRequirement,
    ServiceFormField,
    ServicePricingTier,
    ServiceStep,
)

_logger = logging.getLogger(__name__)


def _slugify(label: str) -> str:
    return (
        label.lower()
        .replace("(", "")
        .replace(")", "")
        .replace("/", "-")
        .replace(" ", "-")
        .replace("--", "-")
        .strip("-")
    )[:128]


async def seed_dev_services() -> None:
    if db_manager.session_factory is None:
        return
    async with db_manager.session_factory() as session:
        existing = await session.scalar(select(Service.service_id).limit(1))
        if existing is not None:
            _logger.info("Services already seeded — skipping.")
            return
        seeds = _service_seeds()
        for seed in seeds:
            service_id = generate_id("svc")
            service = Service(
                service_id=service_id,
                slug=seed["slug"],
                name=seed["name"],
                category=seed["category"],
                short_description=seed["lede"],
                description=seed["description"],
                color=COLOUR_HEX_MAP.get(seed["colour"], "#3498DB"),
                icon=seed["slug"],
                status="active",
                version=1,
                is_featured=seed.get("featured", False),
                step2_title=seed["step2_title"],
                step2_lede=seed["step2_lede"],
                created_by=None,
            )
            session.add(service)
            await session.flush()
            for step in seed["steps"]:
                session.add(
                    ServiceStep(
                        id=generate_id("sst"),
                        service_id=service_id,
                        step_number=step["num"],
                        title=step["title"],
                        description=step.get("body"),
                    )
                )
            for idx, req in enumerate(seed["requirements"]):
                session.add(
                    ServiceDocumentRequirement(
                        id=generate_id("sdr"),
                        service_id=service_id,
                        key=_slugify(req["label"]),
                        label=req["label"],
                        description=req.get("note"),
                        doc_type=req["docType"],
                        is_required=req.get("status", "required") != "optional",
                        max_size_mb=10,
                        allowed_mime_types=_default_mimes(req["docType"]),
                        sort_order=idx,
                    )
                )
            for idx, field in enumerate(seed["fields"]):
                options = None
                if field.get("options"):
                    options = [
                        {
                            "value": o["value"],
                            "label": o["label"],
                            **({"description": o["description"]} if o.get("description") else {}),
                        }
                        for o in field["options"]
                    ]
                conditional_field = None
                conditional_value = None
                if field.get("conditional"):
                    conditional_field = field["conditional"]["field"]
                    conditional_value = field["conditional"]["values"][0]
                session.add(
                    ServiceFormField(
                        id=generate_id("sff"),
                        service_id=service_id,
                        field_key=field["id"],
                        label=field["label"],
                        field_type=field["type"].replace("-", "_"),
                        help_text=field.get("help"),
                        is_required=field.get("required", False) and not field.get("optional"),
                        options=options,
                        conditional_on_field=conditional_field,
                        conditional_on_value=conditional_value,
                        sort_order=idx,
                        max_length=field.get("maxLength"),
                        placeholder=field.get("placeholder"),
                        card_id=field.get("card_id", "default"),
                        card_title=field.get("card_title", "Details"),
                    )
                )
            for tier in seed["pricing_tiers"]:
                session.add(
                    ServicePricingTier(
                        id=generate_id("spt"),
                        service_id=service_id,
                        tier=tier["tier"],
                        display_name=tier["label"],
                        platform_fee=tier["fee"],
                        government_fee=tier.get("government_fee", 0),
                        eta_business_days=tier["eta_days"],
                        features=tier["includes"],
                        is_available=True,
                    )
                )
        await session.commit()
        _logger.info("Seeded %d development services.", len(seeds))


async def seed_platform_settings() -> None:
    if db_manager.session_factory is None:
        return
    from datetime import UTC, datetime

    from app.modules.platform.models import PlatformSettings

    async with db_manager.session_factory() as session:
        existing = await session.get(PlatformSettings, "global")
        if existing is not None:
            _logger.info("Platform settings already seeded — skipping.")
            return
        session.add(PlatformSettings(id="global", updated_at=datetime.now(UTC)))
        await session.commit()
        _logger.info("Seeded global platform settings.")


def _default_mimes(doc_type: str) -> list[str]:
    if doc_type == "photo":
        return ["image/jpeg", "image/png", "image/webp"]
    if doc_type in {"id", "certificate", "proof", "form"}:
        return ["image/jpeg", "image/png", "application/pdf"]
    return ["image/jpeg", "image/png", "application/pdf"]


def _service_seeds() -> list[dict]:
    return [
        {
            "slug": "passport-application",
            "name": "Passport Application",
            "category": "identity",
            "colour": "green",
            "featured": True,
            "lede": "Apply for a new passport or renew an existing one — fully remote.",
            "description": "ProxiServe handles your passport application with the Directorate General of Immigration and Emigration.",
            "step2_title": "Passport details",
            "step2_lede": "Tell us about the passport you need.",
            "steps": [
                {"num": 1, "title": "Submit application", "body": "Complete the online form and upload documents."},
                {"num": 2, "title": "Document review", "body": "Our agent verifies your documents."},
                {"num": 3, "title": "Authority submission", "body": "We submit to DGIE on your behalf."},
                {"num": 4, "title": "Processing", "body": "Track progress while DGIE processes."},
                {"num": 5, "title": "Collection ready", "body": "Your passport is ready for collection."},
            ],
            "requirements": [
                {"label": "National ID", "docType": "id"},
                {"label": "Passport photo", "docType": "photo"},
            ],
            "fields": [
                {
                    "id": "application_type",
                    "label": "Application type",
                    "type": "radio-card",
                    "required": True,
                    "card_id": "type",
                    "card_title": "Application type",
                    "options": [
                        {"value": "new", "label": "New passport", "description": "First-time application"},
                        {"value": "renewal", "label": "Renewal", "description": "Renew an existing passport"},
                    ],
                },
                {
                    "id": "travel_date",
                    "label": "Planned travel date",
                    "type": "date",
                    "required": True,
                    "card_id": "travel",
                    "card_title": "Travel plans",
                },
            ],
            "pricing_tiers": [
                {"tier": "standard", "label": "Standard", "fee": 40000, "eta_days": 10, "includes": ["Document review", "DGIE submission", "Status tracking"]},
                {"tier": "express", "label": "Express", "fee": 60000, "eta_days": 5, "includes": ["Priority processing", "Daily updates"]},
                {"tier": "urgent", "label": "Urgent", "fee": 80000, "eta_days": 2, "includes": ["Same-day submission", "Dedicated agent"]},
            ],
        },
        {
            "slug": "company-registration",
            "name": "Company Registration",
            "category": "business",
            "colour": "blue",
            "lede": "Register your company with RDB without stepping into a government office.",
            "description": "ProxiServe handles your entire company registration with the Rwanda Development Board.",
            "step2_title": "Company details",
            "step2_lede": "Tell us about the company you want to register.",
            "steps": [
                {"num": 1, "title": "Submit your details", "body": "Fill in the online form."},
                {"num": 2, "title": "Name reservation", "body": "We reserve your company name with RDB."},
                {"num": 3, "title": "Document preparation", "body": "We prepare incorporation documents."},
                {"num": 4, "title": "RDB submission", "body": "We submit to RDB on your behalf."},
                {"num": 5, "title": "Certificate delivery", "body": "Digital certificate delivered."},
            ],
            "requirements": [
                {"label": "National ID or Passport", "docType": "id"},
                {"label": "Proposed company name", "docType": "form"},
            ],
            "fields": [
                {
                    "id": "name1",
                    "label": "First choice company name",
                    "type": "text",
                    "required": True,
                    "card_id": "names",
                    "card_title": "Proposed company names",
                    "placeholder": "e.g. Kigali Ventures Ltd",
                },
                {
                    "id": "companyType",
                    "label": "Company type",
                    "type": "select",
                    "required": True,
                    "card_id": "names",
                    "card_title": "Proposed company names",
                    "options": [
                        {"value": "private-limited", "label": "Private Limited Company (Ltd)"},
                        {"value": "partnership", "label": "Partnership"},
                    ],
                },
            ],
            "pricing_tiers": [
                {"tier": "standard", "label": "Standard", "fee": 85000, "eta_days": 6, "includes": ["Name reservation", "RDB submission", "Digital certificate"]},
                {"tier": "express", "label": "Express", "fee": 120000, "eta_days": 3, "includes": ["Priority processing", "Dedicated agent"]},
                {"tier": "urgent", "label": "Urgent", "fee": 135000, "eta_days": 1, "includes": ["Same-day processing", "Direct RDB liaison"]},
            ],
        },
        {
            "slug": "business-permit",
            "name": "Business Permit",
            "category": "permits",
            "colour": "marigold",
            "lede": "Obtain your business operating permit without visiting city hall.",
            "description": "ProxiServe manages your business permit application with the local authority.",
            "step2_title": "Business details",
            "step2_lede": "Tell us about your business.",
            "steps": [
                {"num": 1, "title": "Application submission", "body": "Submit your details and documents."},
                {"num": 2, "title": "Review", "body": "Agent reviews your application."},
                {"num": 3, "title": "Authority submission", "body": "Submitted to local authority."},
                {"num": 4, "title": "Permit issued", "body": "Your permit is ready."},
            ],
            "requirements": [
                {"label": "National ID", "docType": "id"},
                {"label": "Business registration certificate", "docType": "certificate"},
            ],
            "fields": [
                {
                    "id": "business_name",
                    "label": "Registered business name",
                    "type": "text",
                    "required": True,
                    "card_id": "business",
                    "card_title": "Business information",
                },
                {
                    "id": "district",
                    "label": "District",
                    "type": "select",
                    "required": True,
                    "card_id": "business",
                    "card_title": "Business information",
                    "options": [
                        {"value": "gasabo", "label": "Gasabo"},
                        {"value": "kicukiro", "label": "Kicukiro"},
                        {"value": "nyarugenge", "label": "Nyarugenge"},
                    ],
                },
            ],
            "pricing_tiers": [
                {"tier": "standard", "label": "Standard", "fee": 45000, "eta_days": 7, "includes": ["Document review", "Authority submission"]},
                {"tier": "express", "label": "Express", "fee": 65000, "eta_days": 4, "includes": ["Priority processing"]},
                {"tier": "urgent", "label": "Urgent", "fee": 85000, "eta_days": 2, "includes": ["Same-day submission"]},
            ],
        },
        {
            "slug": "national-id",
            "name": "National ID Renewal",
            "category": "identity",
            "colour": "pink",
            "lede": "Renew your Rwandan National ID without leaving home.",
            "description": "ProxiServe manages your renewal application with NIDA on your behalf.",
            "step2_title": "ID details",
            "step2_lede": "Tell us about your current National ID and why you're renewing.",
            "steps": [
                {"num": 1, "title": "Upload documents", "body": "Send photos of required documents."},
                {"num": 2, "title": "Application preparation", "body": "We prepare the renewal form."},
                {"num": 3, "title": "NIDA submission", "body": "Submitted to NIDA."},
                {"num": 4, "title": "Follow-up", "body": "We track your application."},
                {"num": 5, "title": "ID delivery", "body": "Your new ID is delivered."},
            ],
            "requirements": [
                {"label": "Old or expired National ID", "docType": "id"},
                {"label": "Passport-size photo", "docType": "photo"},
            ],
            "fields": [
                {
                    "id": "reason",
                    "label": "Why are you renewing?",
                    "type": "radio-card",
                    "required": True,
                    "card_id": "reason",
                    "card_title": "Reason for renewal",
                    "options": [
                        {"value": "expired", "label": "It's expired"},
                        {"value": "lost", "label": "I lost it"},
                    ],
                },
            ],
            "pricing_tiers": [
                {"tier": "standard", "label": "Standard", "fee": 25000, "eta_days": 7, "includes": ["Document verification", "NIDA submission"]},
                {"tier": "express", "label": "Express", "fee": 35000, "eta_days": 4, "includes": ["Priority lane submission"]},
                {"tier": "urgent", "label": "Urgent", "fee": 45000, "eta_days": 2, "includes": ["Dedicated agent"]},
            ],
        },
        {
            "slug": "tin-registration",
            "name": "TIN Registration",
            "category": "tax",
            "colour": "marigold",
            "lede": "Get your Tax Identification Number from RRA in 2–3 days, fully remote.",
            "description": "ProxiServe handles your TIN registration with the Rwanda Revenue Authority.",
            "step2_title": "TIN details",
            "step2_lede": "Tell us what type of TIN you need.",
            "steps": [
                {"num": 1, "title": "Provide details", "body": "Share your ID and address details."},
                {"num": 2, "title": "Application preparation", "body": "We prepare your RRA application."},
                {"num": 3, "title": "RRA submission", "body": "Submitted to RRA."},
                {"num": 4, "title": "TIN delivery", "body": "Your TIN certificate is delivered."},
            ],
            "requirements": [
                {"label": "National ID or Passport", "docType": "id"},
                {"label": "Proof of address", "docType": "proof"},
            ],
            "fields": [
                {
                    "id": "tinType",
                    "label": "What kind of TIN do you need?",
                    "type": "radio-card",
                    "required": True,
                    "card_id": "tinType",
                    "card_title": "TIN type",
                    "options": [
                        {"value": "personal", "label": "Personal TIN"},
                        {"value": "business", "label": "Business TIN"},
                    ],
                },
            ],
            "pricing_tiers": [
                {"tier": "standard", "label": "Standard", "fee": 20000, "eta_days": 3, "includes": ["RRA submission", "TIN certificate delivery"]},
                {"tier": "express", "label": "Express", "fee": 28000, "eta_days": 1, "includes": ["Same-day submission"]},
                {"tier": "urgent", "label": "Urgent", "fee": 35000, "eta_days": 1, "includes": ["Dedicated agent"]},
            ],
        },
    ]
