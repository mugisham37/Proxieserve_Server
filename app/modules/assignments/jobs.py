"""Auto-assignment background job."""

from __future__ import annotations

from app.core.database import db_manager
from app.core.jobs import job_queue_manager
from app.core.logging import get_logger
from app.modules.applications.repository import ApplicationsRepository
from app.modules.assignments.service import AssignmentsService

logger = get_logger("auto_assign")


async def auto_assign_application_job(ctx: dict[str, object], *, application_id: str) -> None:
    if db_manager.session_factory is None:
        raise RuntimeError("DatabaseManager is not configured")
    async with db_manager.session_factory() as session:
        apps_repo = ApplicationsRepository(session)
        app = await apps_repo.get_by_id(application_id)
        if app is None or app.assigned_agent_id is not None:
            return
        service = AssignmentsService(session=session, job_queue=job_queue_manager)
        winner_id, score = await service.score_agents(app)
        if winner_id is None:
            await service.notify_no_agent_available(app, score)
            await session.commit()
            return
        await service.do_assign(
            app=app,
            agent_id=winner_id,
            performed_by=winner_id,
            performed_by_role="system",
            note="Auto-assigned by scoring algorithm",
        )
        await session.commit()
        agent = await service.auth_repo.get_user_by_id(winner_id)
        if agent:
            await service.send_assignment_emails(app, agent, None)
