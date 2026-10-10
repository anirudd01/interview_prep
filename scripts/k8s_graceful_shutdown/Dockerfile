# syntax=docker/dockerfile:1
#
# Multi-stage build (Round 2 Q62 refresher).
# Stage 1 builds wheels - this is where compilers / build deps would live if any
# dependency needed them (psycopg, numpy from source, ...). Stage 2 installs only
# the finished wheels, so build tooling never ships in the runtime image.
# For this tiny app the size win is small; the pattern is what matters.

FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
# Dependencies before source code: this layer stays cached when only app.py changes.
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index /wheels/* && rm -rf /wheels
COPY app.py loadgen.py ./
USER 10001
EXPOSE 8000

# EXEC FORM IS MANDATORY FOR GRACEFUL SHUTDOWN.
#   CMD ["python", "app.py"]   -> python is PID 1 and receives SIGTERM directly.
#   CMD python app.py          -> /bin/sh -c is PID 1; sh does NOT forward SIGTERM,
#                                 the app never drains, and kubelet SIGKILLs it
#                                 after terminationGracePeriodSeconds.
# PID 1 also gets no default signal handling from the kernel - fine here because
# uvicorn installs handlers. For apps that don't, use `tini` as the entrypoint.
CMD ["python", "app.py"]
