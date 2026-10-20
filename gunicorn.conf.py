# -*- coding: utf-8 -*-
"""
Nastavenie gunicornu pre hosting (Dockerfile ho spúšťa automaticky).

Jeden worker, viac vlákien: analýza videa beží vo vláknach priamo v procese
servera a jej stav (job_id → priebeh) je v pamäti, takže druhý proces by
o rozpracovaných úlohách nevedel. SQLite tiež znesie jeden proces najlepšie.
"""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers = 1
worker_class = 'gthread'
threads = int(os.getenv('WEB_THREADS', '8'))
# Nahrávanie videa do 600 MB cez pomalšie pripojenie môže trvať dlho.
timeout = 900
graceful_timeout = 60
keepalive = 5
accesslog = '-'
errorlog = '-'
loglevel = 'info'
# Veľké hlavičky nie sú potrebné; limit tela požiadavky rieši Flask (MAX_CONTENT_LENGTH).
limit_request_line = 8190
preload_app = False
