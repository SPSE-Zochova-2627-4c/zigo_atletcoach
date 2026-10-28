# Knižnice a písma uložené v `static/vendor`

Všetko, čo prehliadač pri otvorení AtletCoach načítava, je uložené tu – z prehliadača používateľa nejde
žiadna požiadavka na Google Fonts ani na CDN (výnimka: dlaždice mapy na stránke Heatmapa z CARTO).
Každý súbor je nezmenená kópia z uvedeného zdroja; licenčné texty sú v `licenses/`.

| Súbor | Čo to je | Verzia | Licencia | Zdroj |
|---|---|---|---|---|
| `js/tailwind.js` | Tailwind CSS (Play CDN skript s pluginmi forms a container-queries) | 3.4.17 | MIT – `licenses/tailwindcss-MIT.txt` | https://cdn.tailwindcss.com?plugins=forms,container-queries |
| `js/chart.umd.js` | Chart.js | 4.4.4 | MIT – `licenses/chart.js-MIT.txt` | https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.js |
| `js/leaflet.js`, `js/leaflet.css`, `js/images/` | Leaflet | 1.9.4 | BSD-2-Clause – `licenses/leaflet-BSD-2.txt` | https://unpkg.com/leaflet@1.9.4/dist/ |
| `js/leaflet-heat.js` | Leaflet.heat | 0.2.0 | BSD-2-Clause – `licenses/leaflet.heat-BSD-2.txt` | https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js |
| `fonts/ibm-plex-sans-*.woff2`, `fonts/ibm-plex-mono-*.woff2` | písma IBM Plex Sans (400 – 700) a IBM Plex Mono (400 – 600), latin + latin-ext | Google Fonts | SIL OFL 1.1 – `licenses/ibm-plex-OFL.txt` | https://github.com/IBM/plex |
| `fonts/material-symbols-outlined-*.woff2` | ikony Material Symbols Outlined – podmnožina len s ikonami, ktoré appka používa | Google Fonts | Apache 2.0 – `licenses/material-symbols-Apache-2.0.txt` | https://fonts.google.com/icons |
| `fonts/fonts.css` | `@font-face` pravidlá pre súbory vyššie (z CSS Google Fonts, len cesty zmenené na lokálne) | – | – | – |

Logá Stravy v `static/strava/` sú nezmenené súbory z oficiálneho balíka *1.2-Strava-API-Logos*
(https://developers.strava.com/guidelines/) a používajú sa podľa pravidiel značky Strava.
Mapové dáta: © OpenStreetMap contributors (ODbL), dlaždice © CARTO – atribúcia je priamo v mape.
