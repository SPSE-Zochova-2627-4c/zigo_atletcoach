# DESIGN.md – AtletCoach „Modrá dráha“

Vizuálny jazyk AtletCoach vo formáte [DESIGN.md](https://getdesign.md/what-is-design-md) (9 sekcií podľa
[awesome-claude-design](https://github.com/VoltAgent/awesome-claude-design)). Súbor opisuje, **ako má appka
vyzerať a hýbať sa a prečo**, aby každá nová stránka – nech ju píše človek alebo AI – ostala v rovnakom systéme.
Tokeny a komponenty sú naprogramované v `static/css/src/` (zdroj) → `static/css/app.css` (zostavené, `npm run css`).

Systém nie je kópia žiadnej značky. Vychádza z toho, čo atlét vidí na štadióne: **modrá dráha** s bielymi
čiarami (ako na Hayward Field v Eugene, odkiaľ sú fotky na úvodnej stránke), **svetelná tabuľa** s časmi
a **cieľová kamera (fotofiniš)**, ktorá – rovnako ako naša analýza videa a stopky s fotobunkou – meria čas z obrazu.

---

## 1. Atmosféra

- Večerný štadión: bočné menu je **tmavomodré** ako tribúna po zotmení, aktívna položka svieti modro-tyrkysovým
  prechodom ako svetelná tabuľa. Obsah je svetlý a pokojný, aby sa v ňom dalo čítať veľa časov naraz.
- Appka je **živá, ale nie rušivá**: stránky do seba plynulo prechádzajú, čísla sa pri zobrazení napočítajú,
  ovál týždňa sa nakreslí. Všetko krátke (do 1 s) a raz – nič neblikne v slučke, kým na to nekliknete.
- Na úvodnej stránke sú **skutočné fotky** autora appky z MS do 20 rokov v Eugene 2026 a **animovaný bežec**
  (kostra z analýzy videa) – ukazujú, pre koho appka je a čo vie, bez vymyslených ilustrácií.
- Hustota stredná až vyššia – tréner chce vidieť výsledky celej skupiny, nie reklamné bloky.

## 2. Farby a ich úlohy

| Token | Svetlý | Tmavý | Úloha |
|---|---|---|---|
| `--c-track` | `#1F4BFF` | `#4D74FF` | elektrická modrá: značka, tlačidlá, odkazy, aktívny stav |
| `--c-track-deep` | `#1336D6` | `#3A5CF0` | začiatok prechodu, stlačený stav |
| `--c-cyan` | `#00C2FF` | `#22D3FF` | tyrkys: druhý koniec prechodu, svetlá na tabuli |
| `--c-hot` | `#FF6B2C` | `#FF7A3D` | oranžová: osobný rekord (PB), víťaz vo fotofiniši, kontakt so zemou |
| `--c-navy` | `#0B1A3A` | `#040B1A` | bočné menu, tmavé panely (hero, bežec) |
| `--c-bg` | `#F2F6FC` | `#060E20` | pozadie stránky |
| `--c-surface` | `#FFFFFF` | `#0D1A33` | karty, tabuľky, formuláre |
| `--c-text` | `#0A1A33` | `#EAF1FF` | text |
| `--c-muted` | `#5A6B85` | `#94A6C8` | popisky, sekundárny text (≥ 4,5 : 1) |
| `--c-line` | `#DDE6F3` | `#1C2C4D` | čiary, okraje |
| `--c-infield` | `#067A55` | `#34D399` | splnené, v poriadku |
| `--c-warn` | `#B45309` | `#FBBF24` | sledovať, čaká |
| `--c-danger` | `#D92D4A` | `#FB7185` | chyba, mazanie |
| `--c-info` | `#0B6BCB` | `#60A5FA` | informácia |

Prechody (`tokens.css`):
- `--grad` modrá → tyrkys: tenké pásy bez textu (čiara pod nadpisom, priebeh týždňa, ovál cez `url(#grad-draha)`).
- `--grad-deep` tmavomodrá → modrá → tyrkys: všetko, na čom je **biely text** (aktívna položka menu, avatar,
  bubliny, číslice krokov), aby text mal kontrast aspoň 4,5 : 1.
- `--grad-hot` oranžová → jantárová: iba PB a víťaz – oranžová znamená „najlepší výkon“, nikdy chybu.

Pravidlá:
- Stav nesie vždy aj text alebo tvar (PB, ✓, popis), nie iba farba.
- Hlavné tlačidlo je modré s prechodom; pri prejdení myšou sa prechod posunie a cez tlačidlo prebehne lesk.
  Mazanie je červený obrys, aby sa „Uložiť“ a „Zmazať“ nedali zameniť.
- Grafy: série v poradí modrá → tyrkys → oranžová → zelená (`--series-1..4`), v tmavom režime svetlejšie.

## 3. Typografia

Jedna rodina: **Archivo** (variabilné písmo, osi hrúbka 100–900 a šírka 62–125 %, SIL OFL, latin + latin-ext,
všetky slovenské znaky). Dve jasne odlišné polohy – **úzke a ťažké** ako čísla na svetelnej tabuli,
**normálne** na čítanie:

| Rola | Šírka | Hrúbka | Veľkosť | Použitie |
|---|---|---|---|---|
| Titulok úvodnej stránky | 66 % | 850 | 46–84 px / 0,92 | `.hero-title` |
| Titulok stránky | 74 % | 800 | 44 px / 1,0 | `.page-title` |
| Nadpis sekcie na úvode | 70 % | 820 | 34–54 px | `.sec-head h2` |
| Nadpis sekcie | 80 % | 720 | 19 px | `.rule` |
| Číslo na tabuli | 74 % | 760 | 46 px, tabulárne číslice | `.kpi-value`, `.score-num` |
| Čas v tabuľke | 88 % | 560 | 15 px, tabulárne číslice | `.mono`, bunky tabuliek |
| Text | 100 % | 400 | 15–17 px / 1,55 | odstavce, formuláre |
| Popis | 100 % | 560–650 | 12,5–13 px | popisky polí, hlavičky tabuliek |

- **Žiadne verzálky v popiskoch**, žiadne prestrkávanie písmen, žiadne strojopisné písmo na dáta.
  Verzálkami sa píšu iba skratky, ktoré tak naozaj vyzerajú (PB, SB, HRV).
- Riadok textu max. ~70 znakov. Nadpisy na úvode `text-wrap: balance`, odstavce `pretty` (bez osamotených slov).
- Časy sa vždy zarovnávajú doprava a majú tabulárne číslice, aby stotiny ležali pod sebou.

## 4. Komponenty

- **Bočné menu**: tmavomodré, skupiny oddelené jemnou čiarou. Aktívna položka je svietiaci modrý blok,
  položka sa pri prejdení myšou posunie o 3 px. Dole avatar s iniciálou, meno, rola, odhlásenie, téma.
- **Hlavička stránky** `.page-head`: titulok vľavo, pod ním jedna veta kontextu, akcie vpravo.
  Bez „eyebrow“ nadpisov nad titulkom.
- **Tabuľa čísel** `.kpi-strip`: jeden rám rozdelený čiarami, nie samostatné karty; čísla sa napočítajú.
- **Karta** `.card`: biela, okraj 1 px, rádius 16 px, jemný modrastý tieň. Klikateľná karta sa nadvihne.
- **Tabuľka** = výsledková listina: hlavička na svetlom podklade, riadky oddelené 1 px, čísla vpravo,
  riadok sa pri prejdení myšou jemne podfarbí. Na úvodnej stránke sa na mobile mení na karty (`data-label`).
- **Tlačidlá** sú pilulky: `.btn-primary` (modrý prechod so žiarou), `.btn-secondary` (biele s okrajom),
  `.btn-ghost`, `.btn-danger`; text je veta („Uložiť výsledok“, nie „Odoslať“). Po kliknutí sa rozbehne vlna.
- **Štítky** `.chip`: pilulky s bodkou; `ok` / `warn` / `bad` / `accent` / `info`. **PB** je oranžová pilulka.
- **Ovál 400 m** (makro `oval` v `_ui.html`): priebeh týždňa ako kus kola od cieľovej čiary, ťah prechodom.
- **Hlásenia**: biela karta s 4 px farebným okrajom vľavo, vyskočí pružinou; úspech zmizne sám, chyba ostane.
- **Formuláre**: rádius 10 px; pole, v ktorom píšeš, má modrý okraj a modrý prstenec 4 px.
- **Fotky** (`static/img/fotky/`, WebP 800/1600 alebo 450/900 cez `srcset`, bez metadát): hero na úvode,
  koláž „Appku robí bežec“, fotka štadióna vedľa prihlásenia (makro `auth_photo`).

## 5. Rozloženie

- Desktop: menu 252 px vľavo + obsah s max. šírkou 1240 px, všetko zarovnané doľava.
- Mriežka 4 px; medzery 8 · 12 · 16 · 24 · 32 · 48; sekcie úvodnej stránky 96 px od seba.
- Úvod: hero je **delený** – text na tmavomodrej vľavo, fotky vpravo, fotka sa do modrej stráca maskou.
  Funkcie sú v mriežke kariet rôznej šírky (`.bento`), každá karta má malú ukážku toho, čo appka zobrazí.
- Sekcie oddeľuje nadpis s čiarou a krátkym modrým pásom pod ním (`.rule`), nie farebné boxy.
- Číslovanie (1 2 3 4) iba tam, kde je obsah naozaj postup („Ako začať ako tréner“).

## 6. Hĺbka a pohyb

Hĺbka: karty majú jemný tieň s modrým nádychom (`--shadow-1`), čo pláva vyššie, má `--shadow-2`;
hlavné tlačidlo a aktívna položka menu žiaria (`--shadow-glow`). Za obsahom sa veľmi pomaly vlní modrá
„polárna žiara“ (`.main-col::before`, 26 s), ktorá dáva svetlému pozadiu hĺbku.

Pohyb (`static/css/src/motion.css`, `static/js/app.js`, `static/js/bezec.js`):

| Kde | Čo sa hýbe | Trvanie |
|---|---|---|
| Prechod medzi stránkami | stará stránka zmizne nahor, nová vyjde zdola; menu stojí, titulok sa presunie (View Transitions) | 0,22 + 0,42 s |
| Prepnutie témy | celá stránka sa prelinie do tmavej / svetlej | 0,4 s |
| Načítanie stránky | bloky stránky vychádzajú postupne po 70 ms | 0,7 s |
| Scrollovanie | bloky pod okrajom obrazovky sa vysunú, keď k nim prídeš | 0,8 s |
| Čísla na tabuli | napočítajú sa od nuly | 0,9 s |
| Ovál a pásy týždňa | nakreslia sa od štartu | 0,5–1,6 s |
| Úvod: fotky | prelínajú sa každých 7 s, pomaly sa približujú (Ken Burns), pri scrollovaní idú pomalšie (paralaxa) | 16 s cyklus |
| Úvod: bežec | kostra bežca beží 4× spomalene, HUD ukazuje fázu kroku a uhol v kolene | nepretržite, len keď je vidieť |
| Úvod: fotofiniš | čiara kamery prebehne dráhami, pri bežcoch sa ukážu časy | raz, 1,8 s |
| Tlačidlo | nadvihne sa, prebehne lesk, po kliknutí vlna | 0,25–0,8 s |

- `prefers-reduced-motion: reduce` vypne všetko z tabuľky: obsah je hneď viditeľný, bežec stojí
  v jednej polohe, fotky sa nestriedajú, fotofiniš ukáže rovno výsledok.
- Animácie bežia len vtedy, keď je prvok na obrazovke (IntersectionObserver), aby nezaťažovali telefón.

## 7. Áno / nie

Áno: modrá dráha a svetelná tabuľa, skutočné fotky z pretekov, časy s tabulárnymi číslicami, PB v oranžovej,
krátky zmysluplný pohyb, vecné slovenské texty.

Nie: vymyslené ilustrácie ľudí, fotky z fotobánk, sklo/blur ako výplň všade (iba na popisoch nad fotkou),
ikonky v zaoblených štvorčekoch nad každou kartou, verzálkové popisky s rozostupmi, „→“ za odkazmi,
reťazce „A · B · C“ ako ozdoba, emoji v rozhraní, nekonečné blikanie a poskakovanie.

## 8. Responzívnosť

- Pod 1024 px sa menu zmení na tmavomodrý pás hore s tlačidlom menu; menu sa vysúva zľava.
- Úvod na mobile: fotka hore, titulok ju prekrýva zdola; bežec nad textom; tabuľka „Kto čo vidí“ sa zmení na karty.
- Dotykové ciele min. 40 × 40 px, široké tabuľky sa posúvajú vodorovne vo vlastnom kontajneri.
- Svetlý aj tmavý režim; voľba sa pamätá v prehliadači, inak podľa systému.

## 9. Pokyny pre AI agenta

- „Pridaj stránku v štýle AtletCoach“: použi `.page-head`, `.card`, `.rule`, tabuľku `w-full` a tokeny
  z tohto súboru; nepridávaj nové farby ani písma.
- Biely text daj iba na `--grad-deep` alebo `--c-track`, nikdy na čistý tyrkys.
- Čísla a časy vždy `.mono` (tabulárne Archivo), vpravo. Čísla, ktoré sa majú napočítať, dostanú `data-count`.
- Nový pohyb pridaj iba ako odpoveď na akciu používateľa alebo raz pri zobrazení; vždy s variantom
  pre `prefers-reduced-motion`.
- Prázdny stav = jedna veta, čo sa stane, a tlačidlo, ktoré to spraví („Pridať prvý výsledok“).
- Chybové hlásenie povie, čo sa stalo a ako to opraviť; neospravedlňuje sa.
