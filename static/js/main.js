/* Starší skript z prvej verzie appky. Žiadna šablóna ho momentálne nenačítava
   (prvky #training-form, #trendChart ani #predicted-time v šablónach nie sú).
   Farby grafu berie z dizajnových tokenov v :root, aby pri prípadnom použití
   zapadol do svetlého vzhľadu AtletCoach a nepoužíval cyan / sivé odtiene. */
document.addEventListener("DOMContentLoaded", () => {
    const token = (name, fallback) => {
        const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    };
    const seriesA = token('--series-1', '#c8381d');
    const seriesB = token('--series-2', '#1f6f8b');
    const muted = token('--muted', '#655f53');
    const text = token('--text', '#15140f');
    const grid = token('--border', '#e1dccf');

    // -----------------------------------------
    // 1. Odoslanie formulára a odhad času
    // -----------------------------------------
    const form = document.getElementById("training-form");
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            const val = (id) => (document.getElementById(id) || {}).value || "";
            const payload = {
                training_type: val("training_type"),
                times: val("times"),
                rest_minutes: val("rest_minutes"),
                whoop_hrv: val("whoop_hrv"),
                whoop_recovery: val("whoop_recovery")
            };

            const btn = form.querySelector('button[type="submit"]');
            const original = btn ? btn.textContent : "";
            if (btn) { btn.textContent = "Spracúvam…"; btn.disabled = true; }

            await runPrediction(payload);

            if (btn) { btn.textContent = original || "Uložiť a vyhodnotiť"; btn.disabled = false; }
            form.reset();
        });
    }

    // -----------------------------------------
    // 2. Graf vývoja (Chart.js)
    // -----------------------------------------
    const ctx = document.getElementById("trendChart");
    if (ctx && typeof Chart !== "undefined") {
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['1. máj', '8. máj', '15. máj', '22. máj', '29. máj'],
                datasets: [
                    {
                        label: 'Spomalenie na úsekoch (s medzi 1. a posledným úsekom)',
                        data: [1.2, 1.8, 0.9, 2.3, 0.5],
                        borderColor: seriesA,
                        backgroundColor: 'rgba(200, 56, 29, 0.10)',
                        tension: 0.3,
                        fill: true,
                        yAxisID: 'y'
                    },
                    {
                        label: 'HRV (ms)',
                        data: [58, 45, 66, 42, 72],
                        borderColor: seriesB,
                        backgroundColor: 'rgba(31, 111, 139, 0.10)',
                        tension: 0.3,
                        fill: true,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        grid: { color: grid },
                        ticks: { color: muted },
                        title: { display: true, text: 'Sekundy', color: muted }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: { drawOnChartArea: false },
                        ticks: { color: muted },
                        title: { display: true, text: 'HRV', color: muted }
                    },
                    x: {
                        grid: { color: grid },
                        ticks: { color: muted }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: text }
                    }
                }
            }
        });
    }
});

async function runPrediction(payload = {}) {
    const timeDisplay = document.getElementById("predicted-time");
    if (!timeDisplay) return;
    timeDisplay.setAttribute("aria-busy", "true");

    try {
        const response = await fetch('/api/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.status === "success") {
            timeDisplay.textContent = data.predicted_time.toFixed(2) + " s";
        } else {
            timeDisplay.textContent = "Bez odhadu";
        }
    } catch (e) {
        console.error(e);
        timeDisplay.textContent = "Chyba";
    } finally {
        timeDisplay.removeAttribute("aria-busy");
    }
}
