/* Predvolené nastavenia Chart.js pre všetky grafy v appke (načítava sa hneď za chart.umd.js):
   písmo Archivo s tabulárnymi číslicami a farby z aktuálnej témy. Pri prepnutí témy sa grafy prekreslia. */
(function () {
    'use strict';
    if (!window.Chart) return;
    const css = (name, fallback) =>
        getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    const apply = () => {
        Chart.defaults.locale = 'sk-SK';          // desatinná čiarka a medzery v tisícoch na osiach
        Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
        Chart.defaults.font.size = 12;
        Chart.defaults.color = css('--muted', '#5B6268');
        Chart.defaults.borderColor = css('--border', '#D5D8D4');
    };
    apply();
    document.addEventListener('atletcoach:tema', () => {
        apply();
        Object.values(Chart.instances || {}).forEach((chart) => chart.update('none'));
    });
})();
