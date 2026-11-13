/* AtletCoach – animovaný bežec: kostra šprintéra tak, ako ju vidí analýza videa (body kĺbov ako MediaPipe Pose).
   Kreslí sa do <canvas> v prvku [data-bezec]; HUD prvky [data-hud="…"] dostávajú živé hodnoty
   (fáza kroku, uhol kolena, čas kontaktu). Pohyb je vypočítaný z jednoduchého modelu krokového cyklu:
   uhol stehna a ohnutie kolena v kľúčových bodoch cyklu, medzi nimi plynulá (kosínusová) interpolácia.
   Pri „obmedziť pohyb“ sa nakreslí jeden nehybný snímok. Keď prvok nie je na obrazovke, animácia stojí. */
(function () {
    'use strict';

    // Kľúčové body cyklu pravej nohy: [fáza 0–1, hodnota v stupňoch]. Opora (kontakt so zemou) je 0 – 0,22.
    const THIGH = [[0, 22], [0.11, 0], [0.22, -22], [0.32, -30], [0.5, 10], [0.62, 58], [0.75, 50], [0.9, 32], [1, 22]];
    const KNEE = [[0, 20], [0.08, 38], [0.22, 14], [0.35, 70], [0.48, 128], [0.62, 95], [0.8, 40], [0.92, 18], [1, 20]];
    const PLANTAR = [[0, 18], [0.11, 8], [0.22, 45], [0.4, 30], [0.75, 10], [1, 18]];
    const STANCE_END = 0.22;
    const REAL_CYCLE_S = 0.44;       // dvojkrok pri šprinte ≈ 0,44 s (kadencia ≈ 272 krokov/min)
    const SLOW = 4;                   // prehráva sa 4× spomalene, aby bolo vidno kontakt

    const lerpKeys = (keys, phase) => {
        const p = ((phase % 1) + 1) % 1;
        for (let i = 0; i < keys.length - 1; i++) {
            const [p0, v0] = keys[i], [p1, v1] = keys[i + 1];
            if (p >= p0 && p <= p1) {
                const t = (p - p0) / (p1 - p0);
                return v0 + (v1 - v0) * (1 - Math.cos(Math.PI * t)) / 2;
            }
        }
        return keys[0][1];
    };
    const rad = (deg) => deg * Math.PI / 180;

    function pose(phase, H, hip) {
        // Vráti body jednej strany tela (noha + ruka) pre danú fázu; hip = {x, y}
        const L = { thigh: 0.245 * H, shank: 0.245 * H, foot: 0.085 * H, upper: 0.17 * H, fore: 0.16 * H };
        const t = rad(lerpKeys(THIGH, phase));
        const k = rad(lerpKeys(KNEE, phase));
        const knee = { x: hip.x + L.thigh * Math.sin(t), y: hip.y + L.thigh * Math.cos(t) };
        const s = t - k;                                   // holeň: stehno ohnuté v kolene dozadu
        const ankle = { x: knee.x + L.shank * Math.sin(s), y: knee.y + L.shank * Math.cos(s) };
        const perp = { x: Math.cos(s), y: -Math.sin(s) };  // chodidlo kolmo na holeň, špičkou dopredu
        const pl = rad(lerpKeys(PLANTAR, phase));
        const dir = { x: perp.x * Math.cos(pl) - perp.y * Math.sin(pl), y: perp.x * Math.sin(pl) + perp.y * Math.cos(pl) };
        const toe = { x: ankle.x + L.foot * dir.x, y: ankle.y + L.foot * dir.y };
        const heel = { x: ankle.x - 0.3 * L.foot * dir.x, y: ankle.y - 0.3 * L.foot * dir.y };
        return { knee, ankle, toe, heel, kneeDeg: 180 - lerpKeys(KNEE, phase), L };
    }

    function arm(phase, H, shoulder) {
        const L = { upper: 0.17 * H, fore: 0.16 * H };
        const a = rad(-(lerpKeys(THIGH, phase) - 14) * 0.85);   // ruka ide opačne ako stehno tej istej strany
        const e = rad(88 + 14 * Math.sin(2 * Math.PI * phase));
        const elbow = { x: shoulder.x + L.upper * Math.sin(a), y: shoulder.y + L.upper * Math.cos(a) };
        const wrist = { x: elbow.x + L.fore * Math.sin(a + e), y: elbow.y + L.fore * Math.cos(a + e) };
        return { elbow, wrist };
    }

    function setup(root) {
        const canvas = root.querySelector('canvas');
        if (!canvas || !canvas.getContext) return;
        const ctx = canvas.getContext('2d');
        const hud = (name) => root.querySelector(`[data-hud="${name}"]`);
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const css = (n, f) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f;

        let W = 0, Hc = 0, dpr = 1, H = 0, hipBase = null, groundY = 0, groundSpeed = 0;
        let offset = 0, bokeh = [], running = false, last = 0, phase = 0.55;
        const trail = [];

        function resize() {
            const r = canvas.getBoundingClientRect();
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            W = r.width; Hc = r.height;
            canvas.width = Math.round(W * dpr); canvas.height = Math.round(Hc * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            H = Math.min(Hc * 0.82, W * 0.62);
            hipBase = { x: W * 0.42, y: Hc * 0.16 + 0.31 * H + 0.12 * H };
            // zem: špička opornej nohy v strede opory sa dotýka zeme
            groundY = pose(0.11, H, hipBase).toe.y + 0.035 * H;
            // rýchlosť zeme = ako rýchlo ide oporná špička dozadu, aby noha „stála“ na dráhe
            const a = pose(0.03, H, hipBase).toe.x, b = pose(0.19, H, hipBase).toe.x;
            groundSpeed = (a - b) / (0.16);        // px za jeden cyklus
            bokeh = Array.from({ length: 18 }, (_, i) => ({
                x: (i / 18) * W * 1.2, y: Hc * (0.08 + 0.3 * ((i * 37) % 10) / 10),
                r: 6 + ((i * 53) % 14), a: 0.08 + ((i * 29) % 10) / 60,
            }));
        }

        function hipAt(p) {
            // dva poskoky za cyklus: najnižšie v strede opory každej nohy
            return { x: hipBase.x, y: hipBase.y + 0.022 * H * Math.cos(4 * Math.PI * (p - 0.11)) };
        }

        function line(a, b, color, width) {
            ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round';
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
        function dot(p, color, r) { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill(); }

        function body(p, alpha, withJoints) {
            const hip = hipAt(p);
            const lean = rad(9);
            const T = 0.3 * H;
            const shoulder = { x: hip.x + T * Math.sin(lean), y: hip.y - T * Math.cos(lean) };
            const head = { x: shoulder.x + 0.07 * H * Math.sin(lean), y: shoulder.y - 0.1 * H };
            const far = pose(p + 0.5, H, hip), near = pose(p, H, hip);
            const farArm = arm(p + 0.5, H, shoulder), nearArm = arm(p, H, shoulder);
            const cyan = css('--series-2', '#22D3FF');
            const blue = 'rgba(120,160,255,' + (0.55 * alpha) + ')';
            const white = 'rgba(255,255,255,' + alpha + ')';
            const w = Math.max(2.5, H * 0.016);
            // vzdialená strana (ľavá) – tlmenejšia
            line(hip, far.knee, blue, w); line(far.knee, far.ankle, blue, w); line(far.heel, far.toe, blue, w);
            line(shoulder, farArm.elbow, blue, w); line(farArm.elbow, farArm.wrist, blue, w);
            // trup a hlava
            line(hip, shoulder, white, w * 1.15);
            ctx.strokeStyle = white; ctx.lineWidth = w; ctx.beginPath(); ctx.arc(head.x, head.y, 0.055 * H, 0, Math.PI * 2); ctx.stroke();
            // bližšia strana (pravá) – výrazná
            line(hip, near.knee, white, w * 1.1); line(near.knee, near.ankle, white, w * 1.1); line(near.heel, near.toe, white, w * 1.1);
            line(shoulder, nearArm.elbow, white, w); line(nearArm.elbow, nearArm.wrist, white, w);
            if (withJoints) {
                [hip, near.knee, near.ankle, near.toe, shoulder, nearArm.elbow, nearArm.wrist].forEach((j) => dot(j, cyan, w * 1.05));
                [far.knee, far.ankle, farArm.elbow, farArm.wrist].forEach((j) => dot(j, 'rgba(120,160,255,0.8)', w * 0.8));
            }
            return { hip, near };
        }

        function draw(dtCycles) {
            ctx.clearRect(0, 0, W, Hc);
            // svetlá štadióna v pozadí (posúvajú sa pomalšie – hĺbka)
            bokeh.forEach((b) => {
                b.x -= groundSpeed * dtCycles * 0.12;
                if (b.x < -40) b.x += W * 1.25;
                const g = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r * 3);
                g.addColorStop(0, `rgba(140,190,255,${b.a})`); g.addColorStop(1, 'rgba(140,190,255,0)');
                ctx.fillStyle = g; ctx.beginPath(); ctx.arc(b.x, b.y, b.r * 3, 0, Math.PI * 2); ctx.fill();
            });
            // dráha: modrý pás, biela čiara dráhy a značky, ktoré utekajú dozadu
            const grd = ctx.createLinearGradient(0, groundY, 0, Hc);
            grd.addColorStop(0, 'rgba(31,75,255,0.55)'); grd.addColorStop(1, 'rgba(31,75,255,0.05)');
            ctx.fillStyle = grd; ctx.fillRect(0, groundY, W, Hc - groundY);
            line({ x: 0, y: groundY }, { x: W, y: groundY }, 'rgba(255,255,255,0.65)', 2);
            offset = (offset + groundSpeed * dtCycles) % 140;
            for (let x = -offset; x < W + 140; x += 140) {
                line({ x, y: groundY + 10 }, { x: x - 34, y: Hc }, 'rgba(255,255,255,0.18)', 2);
            }
            // stopa za bežcom (rozmazanie rýchlosti)
            trail.forEach((p, i) => {
                ctx.save(); ctx.translate(-(trail.length - i) * 14, 0);
                body(p, 0.08 + i * 0.05, false); ctx.restore();
            });
            const now = body(phase, 1, true);
            // kontakt so zemou: žiara pod opornou nohou
            const stance = (phase % 1) < STANCE_END;
            if (stance) {
                const c = now.near.toe;
                const g = ctx.createRadialGradient(c.x, groundY, 0, c.x, groundY, 0.12 * H);
                g.addColorStop(0, 'rgba(255,140,60,0.75)'); g.addColorStop(1, 'rgba(255,140,60,0)');
                ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(c.x, groundY, 0.12 * H, 0.03 * H, 0, 0, Math.PI * 2); ctx.fill();
            }
            // oblúk uhla v kolene
            const kn = now.near.knee, hipP = now.hip, an = now.near.ankle;
            const a1 = Math.atan2(hipP.y - kn.y, hipP.x - kn.x), a2 = Math.atan2(an.y - kn.y, an.x - kn.x);
            ctx.strokeStyle = css('--series-3', '#FF8A50'); ctx.lineWidth = 2.5;
            ctx.beginPath(); ctx.arc(kn.x, kn.y, 0.07 * H, Math.min(a1, a2), Math.max(a1, a2)); ctx.stroke();
            return { stance, knee: Math.round(now.near.kneeDeg) };
        }

        let shownPhase = '';
        function updateHud(state) {
            const f = hud('faza'), k = hud('koleno');
            const label = state.stance ? 'kontakt so zemou' : 'letová fáza';
            if (f && shownPhase !== label) { f.textContent = label; f.dataset.state = state.stance ? 'kontakt' : 'let'; shownPhase = label; }
            if (k) k.textContent = state.knee + '°';
        }

        function frame(ts) {
            if (!running) return;
            const dt = last ? Math.min(0.05, (ts - last) / 1000) : 0;
            last = ts;
            const dtCycles = dt / (REAL_CYCLE_S * SLOW);
            phase = (phase + dtCycles) % 1;
            trail.push(phase); if (trail.length > 4) trail.shift();
            updateHud(draw(dtCycles));
            requestAnimationFrame(frame);
        }

        resize();
        const kontakt = hud('kontakt'); if (kontakt) kontakt.textContent = Math.round(REAL_CYCLE_S * STANCE_END * 1000) + ' ms';
        const kadencia = hud('kadencia'); if (kadencia) kadencia.textContent = Math.round(2 * 60 / REAL_CYCLE_S);
        if (reduce) { phase = 0.62; updateHud(draw(0)); return; }
        const start = () => { if (!running) { running = true; last = 0; requestAnimationFrame(frame); } };
        const stop = () => { running = false; };
        new IntersectionObserver((entries) => entries.forEach((e) => (e.isIntersecting ? start() : stop())), { threshold: 0.1 })
            .observe(root);
        window.addEventListener('resize', () => { resize(); if (!running) updateHud(draw(0)); });
        document.addEventListener('atletcoach:tema', () => { if (!running) updateHud(draw(0)); });
        updateHud(draw(0));
    }

    document.querySelectorAll('[data-bezec]').forEach(setup);
})();
