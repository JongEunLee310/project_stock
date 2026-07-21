from app.db.session import SessionLocal
from app.domains.decision_logs.review_trigger_service import (
    DecisionReviewTriggerService,
)
from app.domains.jobs.service import JobRunService


def evaluate_decision_review_triggers_job() -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start("decision_review_trigger_evaluation", None)
        job_run_id = job_run.id
        summary = DecisionReviewTriggerService(db).run_cycle()
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
