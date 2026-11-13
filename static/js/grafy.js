/* Grafy výkonnosti (/grafy). Dáta sú vložené v <script id="grafy-data"> už zo servera,
   takže sa nič nenačítava dodatočne a tabuľka pod grafom ukazuje tie isté čísla.
   Pravidlá (DESIGN.md): jedna os Y na graf, farby sérií z tokenov --series-1 … --series-3
   (tartan → oceľová → tráva), legenda len pri dvoch sériách; dve série sa líšia aj výplňou
   (obrys vs. plná), nie len farbou. Písmo Archivo nastavuje static/js/chart-defaults.js.
   Pri prepnutí témy (udalosť atletcoach:tema) sa grafy zahodia a nakreslia znova s novými farbami.
   Pri „obmedziť pohyb“ v systéme sa grafy nekreslia animovane. */
(function () {
    'use strict';

    const holder = document.getElementById('grafy-data');
    if (!holder || typeof Chart === 'undefined') return;
    const DATA = JSON.parse(holder.textContent);
    const REDUCE_MOTION = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const el = (id) => document.getElementById(id);
    let charts = [];

    // 11.23 → "11.23", 125.4 → "2:05.40" – rovnaké ako fmt_time() v grafy.py.
    function fmtTime(s) {
        if (s === null || s === undefined || isNaN(s)) return '–';
        if (s < 60) return s.toFixed(2);
        const m = Math.floor(s / 60);
        const sec = s - m * 60;
        return m + ':' + (sec < 10 ? '0' : '') + sec.toFixed(2);
    }

    // Farby z dizajnových tokenov aktuálnej témy (static/css/src/tokens.css).
    function palette() {
        const css = getComputedStyle(document.documentElement);
        const tok = (name, fallback) => (css.getPropertyValue(name) || '').trim() || fallback;
        return {
            S1: tok('--series-1', '#1F4BFF'),
            S2: tok('--series-2', '#00A3D9'),
            S3: tok('--series-3', '#FF6B2C'),
            SURFACE: tok('--surface', '#ffffff'),
            MUTED: tok('--muted', '#5A6B85'),
            INK: tok('--text', '#0A1A33'),
            GRID: tok('--border', '#DDE6F3'),
        };
    }

    function draw() {
        const C = palette();

        // Spoločný základ: mriežka a osi ustúpia, dáta idú dopredu.
        function baseOptions({ yTick, tooltipLabel, tooltipAfter, legend = false, reverse = false, beginAtZero = false }) {
            return {
                responsive: true,
                maintainAspectRatio: true,
                animation: REDUCE_MOTION ? false : undefined,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    y: {
                        reverse: reverse,
                        beginAtZero: beginAtZero,
                        grid: { color: C.GRID, drawTicks: false },
                        border: { display: false },
                        ticks: { color: C.MUTED, padding: 10, callback: yTick || ((v) => v) }
                    },
                    x: {
                        grid: { display: false },
                        border: { color: C.GRID },
                        ticks: { color: C.MUTED, maxRotation: 0, autoSkipPadding: 22 }
                    }
                },
                plugins: {
                    legend: {
                        display: legend,
                        position: 'top',
                        align: 'end',
                        labels: { color: C.MUTED, boxWidth: 10, boxHeight: 10, padding: 14 }
                    },
                    tooltip: {
                        // Inverzná bublina: grafitová na svetlom, svetlá na tmavom podklade.
                        backgroundColor: C.INK,
                        borderColor: C.INK,
                        borderWidth: 1,
                        cornerRadius: 3,
                        padding: 10,
                        displayColors: legend,
                        boxWidth: 8, boxHeight: 8,
                        titleColor: C.SURFACE,
                        titleFont: { size: 12, weight: '500' },
                        bodyColor: C.SURFACE,
                        bodyFont: { size: 14, weight: '650' },
                        footerColor: C.SURFACE,
                        footerFont: { size: 12, weight: '400' },
                        callbacks: {
                            label: tooltipLabel || ((c) => c.parsed.y === null ? 'bez záznamu' : String(c.parsed.y)),
                            footer: tooltipAfter || (() => '')
                        }
                    }
                }
            };
        }

        function lineDataset(values, color, extra = {}) {
            return Object.assign({
                data: values,
                borderColor: color,
                backgroundColor: 'transparent',
                borderWidth: 2,
                // monotónna krivka: hladká, ale nikdy neprestrelí nad/pod namerané body
                cubicInterpolationMode: 'monotone',
                spanGaps: true,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: color,
                pointHoverBorderColor: C.SURFACE,
                pointHoverBorderWidth: 2
            }, extra);
        }

        // Stĺpce: hranaté ako zvyšok appky, 1 px medzera cez rámik vo farbe plochy.
        // outline=true nakreslí stĺpec len ako obrys – druhá séria sa tak odlíši aj bez farby.
        function barDataset(label, values, color, outline = false) {
            return {
                label: label,
                data: values,
                backgroundColor: outline ? C.SURFACE : color,
                borderColor: outline ? color : C.SURFACE,
                borderWidth: outline ? 2 : { left: 1, right: 1, top: 0, bottom: 0 },
                borderRadius: 0,
                borderSkipped: 'bottom',
                hoverBackgroundColor: color,
                hoverBorderColor: outline ? color : C.SURFACE,
                maxBarThickness: 44
            };
        }

        const add = (canvas, config) => charts.push(new Chart(canvas, config));

        /* ── Vývoj výsledkov: obrátená os, PB s plnou značkou ── */
        const res = DATA.vysledky;
        if (el('chart-results') && res.values.length) {
            const pbIdx = res.meta.pb_index;
            add(el('chart-results'), {
                type: 'line',
                data: { labels: res.labels, datasets: [lineDataset(res.values, C.S1, {
                    pointRadius: res.values.map((_, i) => (i === pbIdx ? 6 : 3)),
                    pointHoverRadius: res.values.map((_, i) => (i === pbIdx ? 8 : 5)),
                    pointBackgroundColor: res.values.map((_, i) => (i === pbIdx ? C.S1 : C.SURFACE)),
                    pointBorderColor: C.S1,
                    pointBorderWidth: 2
                })]},
                options: baseOptions({
                    reverse: true,
                    yTick: (v) => fmtTime(v),
                    tooltipLabel: (c) => fmtTime(c.parsed.y) + (c.dataIndex === pbIdx ? '  PB' : ''),
                    tooltipAfter: (items) => {
                        const r = res.meta.rows[items[0].dataIndex];
                        if (!r) return '';
                        const parts = [];
                        if (r.competition) parts.push(r.competition);
                        if (r.place) parts.push(r.place + '. miesto');
                        if (r.wind !== null && r.wind !== undefined) parts.push('vietor ' + (r.wind > 0 ? '+' : '') + r.wind.toFixed(1));
                        return parts.join(', ');
                    }
                })
            });
        }

        /* ── Posun PB: bežiace minimum, tiež obrátená os ── */
        const pb = DATA.rekordy;
        if (el('chart-pb') && pb.values.length) {
            add(el('chart-pb'), {
                type: 'line',
                data: { labels: pb.labels, datasets: [lineDataset(pb.values, C.S2, { stepped: 'before', tension: 0 })] },
                options: baseOptions({
                    reverse: true,
                    yTick: (v) => fmtTime(v),
                    tooltipLabel: (c) => 'PB ' + fmtTime(c.parsed.y),
                    tooltipAfter: (items) => {
                        const r = pb.meta.rows[items[0].dataIndex];
                        return r ? 'výsledok ' + r.result + (r.improved ? ', nový rekord' : '') : '';
                    }
                })
            });
        }

        /* ── Tréningový objem: km za týždeň ── */
        const vol = DATA.objem;
        if (el('chart-volume') && vol.meta.total_km > 0) {
            add(el('chart-volume'), {
                type: 'bar',
                data: { labels: vol.labels, datasets: [barDataset('km', vol.values, C.S1)] },
                options: baseOptions({
                    beginAtZero: true,
                    yTick: (v) => v + ' km',
                    tooltipLabel: (c) => c.parsed.y.toFixed(1) + ' km',
                    tooltipAfter: (items) => {
                        const r = vol.meta.rows[items[0].dataIndex];
                        return r ? r.week + ', ' + r.from + ' – ' + r.to + ', ' + r.sessions + ' tréningov' : '';
                    }
                })
            });
        }

        /* ── Plnenie plánu: dve série → legenda áno; naplánované = obrys, splnené = plný stĺpec ── */
        const plan = DATA.plan;
        if (el('chart-plan') && plan.meta.total_planned > 0) {
            add(el('chart-plan'), {
                type: 'bar',
                data: { labels: plan.labels, datasets: [
                    barDataset(plan.meta.series[0], plan.values, C.S2, true),
                    barDataset(plan.meta.series[1], plan.meta.completed, C.S1)
                ]},
                options: Object.assign(baseOptions({
                    legend: true,
                    beginAtZero: true,
                    yTick: (v) => (Number.isInteger(v) ? v : ''),
                    tooltipLabel: (c) => c.dataset.label + ': ' + c.parsed.y,
                    tooltipAfter: (items) => {
                        const r = plan.meta.rows[items[0].dataIndex];
                        return r && r.pct !== null ? 'plnenie ' + r.pct + ' %' : '';
                    }
                }), { datasets: { bar: { categoryPercentage: 0.7, barPercentage: 1.0 } } })
            });
        }

        /* ── Technika: kontakt a kadencia v dvoch samostatných grafoch ── */
        const tech = DATA.technika;
        if (el('chart-contact') && tech.labels.length) {
            add(el('chart-contact'), {
                type: 'line',
                data: { labels: tech.labels, datasets: [lineDataset(tech.values, C.S3, { pointRadius: 3, pointBackgroundColor: C.S3 })] },
                options: baseOptions({
                    yTick: (v) => v + ' ms',
                    tooltipLabel: (c) => c.parsed.y === null ? 'bez hodnoty' : Math.round(c.parsed.y) + ' ms',
                    tooltipAfter: (items) => { const r = tech.meta.rows[items[0].dataIndex]; return r && r.label ? r.label : ''; }
                })
            });
        }
        if (el('chart-cadence') && tech.labels.length) {
            add(el('chart-cadence'), {
                type: 'line',
                data: { labels: tech.labels, datasets: [lineDataset(tech.meta.cadence, C.S3, { pointRadius: 3, pointBackgroundColor: C.S3 })] },
                options: baseOptions({
                    yTick: (v) => v,
                    tooltipLabel: (c) => c.parsed.y === null ? 'bez hodnoty' : Math.round(c.parsed.y) + ' krokov/min',
                    tooltipAfter: (items) => { const r = tech.meta.rows[items[0].dataIndex]; return r && r.label ? r.label : ''; }
                })
            });
        }

        /* ── Posilňovňa: najväčšie kilá na cvik v každom tréningu ── */
        const gym = DATA.posilka;
        if (el('chart-gym') && gym && gym.values.length) {
            add(el('chart-gym'), {
                type: 'line',
                data: { labels: gym.labels, datasets: [lineDataset(gym.values, C.S1, { pointRadius: 3, pointBackgroundColor: C.S1 })] },
                options: baseOptions({
                    beginAtZero: true,
                    yTick: (v) => v + ' kg',
                    tooltipLabel: (c) => c.parsed.y + ' kg',
                    tooltipAfter: (items) => { const r = gym.meta.rows[items[0].dataIndex]; return r ? 'série ' + r.sets + ' kg' + (r.note ? ', ' + r.note : '') : ''; }
                })
            });
        }

        /* ── Úseky z plánu: najrýchlejší čas, obrátená os ── */
        const runs = DATA.behy;
        if (el('chart-runs') && runs && runs.values.length) {
            add(el('chart-runs'), {
                type: 'line',
                data: { labels: runs.labels, datasets: [lineDataset(runs.values, C.S2, { pointRadius: 3, pointBackgroundColor: C.S2 })] },
                options: baseOptions({
                    reverse: true,
                    yTick: (v) => fmtTime(v),
                    tooltipLabel: (c) => fmtTime(c.parsed.y),
                    tooltipAfter: (items) => { const r = runs.meta.rows[items[0].dataIndex]; return r ? r.count + ' úsekov, priemer ' + r.mean : ''; }
                })
            });
        }
    }

    function redraw() {
        charts.forEach((chart) => chart.destroy());
        charts = [];
        draw();
    }

    // Pri prepnutí témy sa grafy nakreslia znova s farbami novej témy (bez obnovenia stránky).
    document.addEventListener('atletcoach:tema', redraw);

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', draw);
    else draw();
})();
