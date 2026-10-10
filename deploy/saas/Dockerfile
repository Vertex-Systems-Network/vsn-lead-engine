# Host-independent build only. Does not provision, configure or deploy a service.
# Pin upstream base-image digests before production release certification.
FROM python:3.12-slim-bookworm AS saas-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv
COPY apps/saas/requirements.txt /tmp/saas-requirements.txt
COPY deploy/saas/requirements-serving.txt /tmp/serving-requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/saas-requirements.txt \
    && python -m pip install --no-cache-dir --require-hashes -r /tmp/serving-requirements.txt
COPY apps/saas/ /srv/apps/saas/
COPY src/ /srv/src/
COPY config/runtime.json /srv/config/runtime.json
USER 10001:10001
WORKDIR /srv/apps/saas

FROM saas-base AS api
EXPOSE 8000
# No full URL/query string is written to access logs.
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--access-logformat", "%(h)s %(s)s %(L)s", "--error-logfile", "-", "lead_saas.wsgi:application"]

FROM saas-base AS worker
USER 0:0
COPY requirements-runtime.txt /tmp/collector-requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/collector-requirements.txt
USER 10001:10001
# One finite batch, then exit; schedule outside the image, never a busy loop.
CMD ["python", "manage.py", "run_jobs", "--limit", "25"]
