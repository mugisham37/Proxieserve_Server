"""Document quality-check background job."""

from __future__ import annotations

from io import BytesIO

import aiofiles
import filetype
from PIL import Image, ImageFilter, ImageStat

from app.core.config import get_settings
from app.core.database import db_manager
from app.core.jobs import job_queue_manager
from app.core.logging import get_logger
from app.core.storage import get_storage
from app.modules.applications.repository import ApplicationsRepository
from app.modules.auth.repository import AuthRepository
from app.modules.documents.repository import DocumentsRepository

logger = get_logger("document_qc")


async def document_qc_job(ctx: dict[str, object], *, document_id: str) -> None:
    settings = get_settings()
    if db_manager.session_factory is None:
        raise RuntimeError("DatabaseManager is not configured")
    storage = get_storage(settings)
    async with db_manager.session_factory() as session:
        repo = DocumentsRepository(session)
        doc = await repo.get_by_id(document_id)
        if doc is None:
            logger.warning("document_qc_not_found", document_id=document_id)
            return
        absolute_path = await storage.open_file(doc.storage_path)
        qc_notes: dict[str, object] = {}
        qc_status = "pass"
        if doc.mime_type.startswith("image/"):
            async with aiofiles.open(absolute_path, "rb") as handle:
                data = await handle.read()
            try:
                image = Image.open(BytesIO(data))
                width, height = image.size
                min_dim = settings.file_qc_min_image_dimension
                qc_notes["dimensions"] = {"width": width, "height": height, "min": min_dim}
                if width < min_dim or height < min_dim:
                    qc_status = "fail"
                    qc_notes["dimensions"]["result"] = "fail"
                else:
                    qc_notes["dimensions"]["result"] = "pass"
                gray = image.convert("L")
                stat = ImageStat.Stat(gray)
                stddev = stat.stddev[0]
                qc_notes["uniformity"] = {"stddev": stddev}
                if stddev < 5:
                    qc_status = "warn" if qc_status == "pass" else qc_status
                    qc_notes["uniformity"]["result"] = "warn"
                else:
                    qc_notes["uniformity"]["result"] = "pass"
                laplacian = gray.filter(ImageFilter.FIND_EDGES)
                lap_var = ImageStat.Stat(laplacian).var[0]
                qc_notes["blur"] = {"laplacian_variance": lap_var}
                if lap_var < 50:
                    qc_status = "warn" if qc_status == "pass" else qc_status
                    qc_notes["blur"]["result"] = "warn"
                else:
                    qc_notes["blur"]["result"] = "pass"
            except Exception as exc:
                qc_status = "fail"
                qc_notes["error"] = str(exc)
        else:
            async with aiofiles.open(absolute_path, "rb") as handle:
                header = await handle.read(261)
            kind = filetype.guess(header)
            qc_notes["mime_verified"] = kind.mime if kind else None
            if kind and kind != doc.mime_type:
                qc_status = "warn"
        doc.qc_status = qc_status
        doc.qc_notes = qc_notes
        await session.commit()
        if qc_status in {"warn", "fail"}:
            auth_repo = AuthRepository(session)
            apps_repo = ApplicationsRepository(session)
            application = await apps_repo.get_by_id(doc.application_id)
            if application is None:
                return
            client = await auth_repo.get_user_by_id(application.client_id)
            if client and client.email and job_queue_manager.redis:
                await job_queue_manager.enqueue(
                    "send_email_job",
                    to=client.email,
                    subject=f"Document needs attention — {application.code}",
                    body=(
                        f"One of your uploaded documents for {application.code} "
                        f"needs attention (QC status: {qc_status}). "
                        "Please log in to review and replace it if needed."
                    ),
                )
