from rq import cron as rq_cron

from app.scheduler.registry import default_scheduler_registry


def _register_cron_jobs() -> None:
    for schedule in default_scheduler_registry.list():
        if schedule.enabled:
            rq_cron.register(schedule.job.func, "default", cron=schedule.cron)


_register_cron_jobs()
