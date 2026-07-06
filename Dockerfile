# --- builder: uv로 의존성만 설치한다 ---
FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- runtime: uv 없이 venv만 사용한다 ---
FROM python:3.12-slim

WORKDIR /app

# builder가 만든 가상환경만 복사한다. uv 바이너리는 런타임 이미지에 포함하지 않는다.
COPY --from=builder /app/.venv /app/.venv

COPY . .

# venv의 실행 파일을 우선 사용해 uvicorn을 직접 실행한다.
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
