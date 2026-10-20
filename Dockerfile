# AtletCoach – obraz pre hosting (Railway, Fly.io, ľubovoľný Docker server).
# Lokálne spúšťanie ostáva cez run.command / run.bat, tento súbor sa ho netýka.
FROM python:3.12-slim

# opencv potrebuje libGL a glib; ffmpeg prekóduje prekryvné video na H.264,
# aby sa dalo prehrať v prehliadači (bez neho appka funguje, video len nehrá všade).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Najprv len závislosti – vrstva sa cachuje, kým sa nezmení requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0

COPY . .

# Trvalé dáta (databáza, secret_key, videá) – na hostingu sem pripoj zväzok (volume).
RUN mkdir -p /app/instance /app/cache
VOLUME ["/app/instance"]

ENV PYTHONUNBUFFERED=1 \
    FLASK_DEBUG=0 \
    ATLETCOACH_RELOAD=0 \
    ATLETCOACH_NO_BROWSER=1 \
    ATLETCOACH_HTTPS=1 \
    PORT=8080

EXPOSE 8080
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
