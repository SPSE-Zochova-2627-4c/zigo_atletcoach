# Knižnice a písma uložené v `static/vendor`

Všetko, čo prehliadač pri otvorení AtletCoach načítava, je uložené tu (okrem `static/css/app.css`, ktorý zostavuje Tailwind CLI) – z prehliadača používateľa nejde
žiadna požiadavka na Google Fonts ani na CDN (výnimka: dlaždice mapy na stránke Heatmapa z CARTO).
Každý súbor je nezmenená kópia z uvedeného zdroja; licenčné texty sú v `licenses/`.

| Súbor | Čo to je | Verzia | Licencia | Zdroj |
|---|---|---|---|---|
| `js/chart.umd.js` | Chart.js | 4.4.4 | MIT – `licenses/chart.js-MIT.txt` | https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.js |
| `js/leaflet.js`, `js/leaflet.css`, `js/images/` | Leaflet | 1.9.4 | BSD-2-Clause – `licenses/leaflet-BSD-2.txt` | https://unpkg.com/leaflet@1.9.4/dist/ |
| `js/leaflet-heat.js` | Leaflet.heat | 0.2.0 | BSD-2-Clause – `licenses/leaflet.heat-BSD-2.txt` | https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js |
| `fonts/archivo-latin*.woff2` | písmo Archivo (variabilné: hrúbka 100 – 900, šírka 62 – 125 %), latin + latin-ext – celé rozhranie | 5.3.0 (Fontsource) | SIL OFL 1.1 – `licenses/archivo-OFL.txt` | https://github.com/Omnibus-Type/Archivo, npm `@fontsource-variable/archivo` |
| `fonts/material-symbols-outlined-*.woff2` | ikony Material Symbols Outlined – podmnožina len s ikonami, ktoré appka používa | Google Fonts | Apache 2.0 – `licenses/material-symbols-Apache-2.0.txt` | https://fonts.google.com/icons |
| `fonts/fonts.css` | `@font-face` pravidlá pre súbory vyššie (z CSS Google Fonts, len cesty zmenené na lokálne) | – | – | – |

Logá a tlačidlá Stravy v `static/strava/` sú nezmenené súbory z oficiálnych balíkov *1.1-Connect-with-Strava-Buttons*
(tlačidlo „Connect with Strava“ na spustenie prihlásenia) a *1.2-Strava-API-Logos* („Powered by Strava“ pri údajoch zo Stravy)
z https://developers.strava.com/guidelines/ a používajú sa podľa pravidiel značky Strava (logá sa nesmú upravovať).
Mapové dáta: © OpenStreetMap contributors (ODbL), dlaždice © CARTO – atribúcia je priamo v mape.

**Tailwind CSS** (MIT – `licenses/tailwindcss-MIT.txt`) sa do prehliadača neposiela ako skript: `npm run css`
z neho zostaví statický súbor `static/css/app.css` (reset prehliadača + utility použité v šablónach).
Verzia je pripnutá v `package.json` (3.4.17).
