from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.signals.service import SignalService


def snapshot_signal_states_job() -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start("signal_snapshot", None)
        job_run_id = job_run.id
        captured_count = SignalService(db).capture_daily_snapshot()
        job_run_service.succeed(job_run.id)
        job_run.metadata_ = {"captured_count": captured_count}
        db.commit()
        return None
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
