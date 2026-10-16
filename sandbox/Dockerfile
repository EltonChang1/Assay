FROM python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip --isolated install --no-cache-dir --no-deps --require-hashes --only-binary=:all: -r /app/requirements.txt
COPY worker.py policy.py /app/
USER 10001:10001
ENTRYPOINT ["python", "-B", "-s", "/app/worker.py"]
