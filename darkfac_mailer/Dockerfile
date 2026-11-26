FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY darkfac_mailer/requirements.txt /app/darkfac_mailer/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/darkfac_mailer/requirements.txt \
    && addgroup --system app \
    && adduser --system --ingroup app --home /app app

COPY darkfac_mailer/__init__.py /app/darkfac_mailer/__init__.py
COPY darkfac_mailer/gsc.py /app/darkfac_mailer/gsc.py
COPY darkfac_mailer/main.py /app/darkfac_mailer/main.py
COPY darkfac_mailer/report.py /app/darkfac_mailer/report.py
COPY darkfac_mailer/templates/ /app/darkfac_mailer/templates/

USER app

CMD ["python", "-m", "darkfac_mailer.main"]
