from app.db.session import SessionLocal
from app.domains.alert_engine.service import AlertEngineService
from app.domains.jobs.service import JobRunService


def evaluate_alert_rules_job() -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start("alert_evaluation", None)
        job_run_id = job_run.id
        summary = AlertEngineService(db).run_cycle()
        job_run_service.succeed(job_run.id)
        job_run.metadata_ = summary.as_metadata()
        db.commit()
        return None
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
