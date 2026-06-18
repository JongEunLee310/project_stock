from rq import Worker

from app.worker.connection import get_redis_connection


def main() -> None:
    Worker(["default"], connection=get_redis_connection()).work()


if __name__ == "__main__":
    main()
