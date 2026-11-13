/* AtletCoach – správanie rámu stránky a pohyb (načítava ho base.html na každej stránke).
   Bez knižníc; každý blok je samostatný a nič nerobí, ak jeho prvky na stránke nie sú.
   Pri „obmedziť pohyb“ v systéme sa animácie vynechajú a obsah sa ukáže hneď. */
(function () {
    'use strict';

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const store = {
        get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
        set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* súkromné okno */ } },
    };

    // ── Bočné menu na mobile: tlačidlo + tmavé pozadie, aria-expanded pre čítačky, Esc zavrie ──
    const menuBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (menuBtn && sidebar) {
        const setOpen = (open) => {
            sidebar.classList.toggle('open', open);
            menuBtn.setAttribute('aria-expanded', String(open));
            if (backdrop) backdrop.hidden = !open;
        };
        menuBtn.addEventListener('click', () => setOpen(!sidebar.classList.contains('open')));
        backdrop?.addEventListener('click', () => setOpen(false));
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setOpen(false); });
    }

    // ── Svetlý / tmavý režim – tlačidiel je viac (menu, mobilný pás), voľba sa pamätá v prehliadači ──
    const root = document.documentElement;
    const themeButtons = document.querySelectorAll('[data-tema-btn]');
    const applyTheme = (theme) => {
        root.setAttribute('data-theme', theme);
        themeButtons.forEach((btn) => {
            btn.setAttribute('aria-pressed', String(theme === 'dark'));
            const icon = btn.querySelector('[data-icon]');
            if (icon) icon.textContent = theme === 'dark' ? 'light_mode' : 'dark_mode';
        });
        // grafy (Chart.js) a animovaný bežec si podľa tejto udalosti prekreslia farby
        document.dispatchEvent(new CustomEvent('atletcoach:tema', { detail: theme }));
    };
    applyTheme(root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
    themeButtons.forEach((btn) => btn.addEventListener('click', () => {
        const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        const swap = () => { applyTheme(next); store.set('atletcoach.tema', next); };
        // prepnutie témy ako plynulý prechod (kde to prehliadač vie)
        if (document.startViewTransition && !reduceMotion) document.startViewTransition(swap); else swap();
    }));

    // ── Hlásenia: dajú sa zavrieť; potvrdenia zmiznú samé po 8 s, chyby a upozornenia ostanú ──
    document.querySelectorAll('[data-flash-close]').forEach((btn) => {
        btn.addEventListener('click', () => btn.closest('.flash-msg')?.remove());
    });
    setTimeout(() => {
        document.querySelectorAll('.flash-msg[data-category="success"], .flash-msg[data-category="info"], .flash-msg[data-category="message"]')
            .forEach((el) => el.remove());
    }, 8000);

    // ── Informačná lišta o cookies – raz zavretá sa už neukáže (len v tomto prehliadači) ──
    const cookieBar = document.getElementById('cookie-lista');
    if (cookieBar) {
        if (store.get('atletcoach.cookies-ok') !== '1') cookieBar.hidden = false;
        document.getElementById('cookie-ok')?.addEventListener('click', () => {
            cookieBar.hidden = true;
            store.set('atletcoach.cookies-ok', '1');
        });
    }

    // ── Striedanie fotiek [data-slideshow]: snímky .slide sa prelínajú každých 7 s,
    //    ukazovateľ [data-dots] má pre každú snímku dielik, ktorý sa plní (CSS) ──
    document.querySelectorAll('[data-slideshow]').forEach((box) => {
        const slides = box.querySelectorAll('.slide');
        const dots = box.querySelectorAll('[data-dots] > span');
        if (slides.length < 2 || reduceMotion) return;
        let i = 0;
        const show = (n) => {
            slides[i].classList.remove('on'); dots[i]?.classList.remove('on');
            i = n % slides.length;
            slides[i].classList.add('on');
            if (dots[i]) { void dots[i].offsetWidth; dots[i].classList.add('on'); }   // reštart plnenia dielika
        };
        setInterval(() => show(i + 1), 7000);
    });

    // ── Vlna po kliknutí na tlačidlo ──
    document.addEventListener('pointerdown', (e) => {
        const btn = e.target.closest?.('.btn');
        if (!btn || reduceMotion || btn.disabled) return;
        const r = btn.getBoundingClientRect();
        const wave = document.createElement('span');
        wave.className = 'ripple';
        wave.style.left = (e.clientX - r.left) + 'px';
        wave.style.top = (e.clientY - r.top) + 'px';
        btn.appendChild(wave);
        wave.addEventListener('animationend', () => wave.remove());
    });

    if (reduceMotion) return;

    // ── Postupné objavenie blokov stránky po načítaní ──
    const main = document.querySelector('#obsah > main') || document.getElementById('obsah');
    const blocks = main ? Array.from(main.children).filter((el) => el.offsetParent !== null) : [];
    const fold = window.innerHeight * 0.92;
    let order = 0;
    blocks.forEach((el) => {
        if (el.getBoundingClientRect().top < fold) {
            el.classList.add('anim-in');
            el.style.setProperty('--i', String(Math.min(order++, 8)));
        } else {
            el.classList.add('reveal');
        }
    });
    // karty a riadky dlhých stránok sa objavia, keď k nim doscrolluješ
    document.querySelectorAll('[data-reveal]').forEach((el) => {
        if (el.getBoundingClientRect().top >= fold) el.classList.add('reveal');
    });
    const io = new IntersectionObserver((entries) => entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        countUp(entry.target);
        io.unobserve(entry.target);
    }), { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

    // ── Napočítanie čísel na tabuliach (44, 78 %, 24.12 …) ──
    const NUM = /^(\d{1,3}(?:[  ]\d{3})*|\d+)([.,]\d+)?$/;
    function countUp(scope) {
        scope.querySelectorAll('.kpi-value, .score-num, [data-count]').forEach((el) => {
            if (el.dataset.counted) return;
            el.dataset.counted = '1';
            const node = Array.from(el.childNodes).find((n) => n.nodeType === 3 && n.textContent.trim());
            if (!node) return;
            const raw = node.textContent.trim();
            const m = raw.match(NUM);
            if (!m) return;
            const decimals = m[2] ? m[2].length - 1 : 0;
            const sep = m[2] ? m[2][0] : '';
            const target = parseFloat(raw.replace(/[  ]/g, '').replace(',', '.'));
            if (!isFinite(target) || target === 0) return;
            const t0 = performance.now(), dur = 900;
            const fmt = (v) => { let s = v.toFixed(decimals); return sep === ',' ? s.replace('.', ',') : s; };
            const step = (now) => {
                const p = Math.min(1, (now - t0) / dur);
                node.textContent = fmt(target * (1 - Math.pow(1 - p, 3)));
                if (p < 1) requestAnimationFrame(step); else node.textContent = raw;
            };
            requestAnimationFrame(step);
        });
    }
    blocks.filter((el) => el.classList.contains('anim-in')).forEach((el) => countUp(el));

    // ── Paralaxa: prvky [data-parallax="0.25"] sa pri scrollovaní posúvajú pomalšie ako stránka.
    //    Posun sa ráta od stredu obrazovky k stredu rodiča (rodič sa nehýbe, takže meranie neskáče)
    //    a je obmedzený rezervou, o ktorú je prvok väčší ako rodič – na okraji nevznikne medzera. ──
    const par = Array.from(document.querySelectorAll('[data-parallax]'));
    if (par.length) {
        let ticking = false;
        const update = () => {
            const mid = window.innerHeight / 2;
            par.forEach((el) => {
                const box = el.parentElement.getBoundingClientRect();
                if (box.bottom < -200 || box.top > window.innerHeight + 200) return;
                const extra = (el.offsetHeight - el.parentElement.offsetHeight) / 2;
                const max = extra > 4 ? extra : 80;
                const shift = (mid - (box.top + box.height / 2)) * parseFloat(el.dataset.parallax || '0.2');
                el.style.setProperty('--par', Math.max(-max, Math.min(max, shift)).toFixed(1) + 'px');
            });
            ticking = false;
        };
        const ask = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
        window.addEventListener('scroll', ask, { passive: true });
        window.addEventListener('resize', ask);
        update();
    }
})();
