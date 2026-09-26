# Audyt twierdzeń: README → zastrzeżenie, testy, DSP, naprawione błędy, parametry, alert KHIPU (TIMDR-Bio-Signals)

Silnik: claim_audit v0.2 (TIMDR-AI-Core).

Wygenerowano: 2026-09-26 12:31 UTC; reguły: `docs/audit/CLAIM_AUDIT_PREREG.md` (sha256 1d995093a9b1), karty: `claims_bio.py` (sha256 f07488b133c3), README sha256 b70d279f2927.

Werdykty kart: POTWIERDZONE 32, SPRZECZNE 7.

## Twierdzenia

| # | Twierdzenie (cytat z README) | Werdykt | Przeliczenie | Uwagi |
| --- | --- | --- | --- | --- |
| Z1 | Wszystkie dane demonstracyjne w tym repo są **w całości syntetyczne** (generowane matematycznie, `demo_scenarios.py`) — żadne prawdziwe dane pacjenta nie zostały użyte | POTWIERDZONE | pliki danych w repo: brak; demo z numpy.random | R13 |
| T1 | 85/85 testów przechodzi (`test_bio_core.py` + `test_demo_scenarios.py` + `test_dsp.py` + `test_khipu_bio_alert.py` + `test_api_khipu.py` | POTWIERDZONE | 85 testów w 7 plikach; ['85 passed in 4.62s'] | KOD REPO |
| F1 | przetwarzanie tego samego sygnału w jednym wywołaniu vs. w dwóch porcjach daje IDENTYCZNY wynik (różnica < 1e-9) | POTWIERDZONE | maks. różnica 0.0e+00 | konfiguracja z test_dsp.py |
| F2 | na granicy porcji powstaje widoczny skok (>0.01 różnicy amplitudy) | POTWIERDZONE | skok na granicy 1,204 | konfiguracja z test_dsp.py |
| F3 | Klasyczny algorytm (Pan & Tompkins, 1985): filtr 5-15Hz → pochodna → kwadrat → całkowanie w oknie ~150ms | POTWIERDZONE | docstring i kod pan_tompkins_qrs: 5-15 Hz, okno ~150 ms | KOD; rok publikacji jako DOKUMENT |
| F4 | wolnego dryfu linii bazowej (0.3Hz, amplituda porównywalna z QRS | POTWIERDZONE | dryf 0,3 Hz, amplituda 0,6 | konfiguracja z test_dsp.py |
| F5 | traci większość uderzeń: **70 → 18 wykrytych** | POTWIERDZONE | detect_peaks: 70 → 18 | KOD REPO |
| F6 | pozostaje w pełni stabilny: **70 → 70 wykrytych** (pasmo 5-15Hz usuwa dryf PRZED wykrywaniem szczytów) | POTWIERDZONE | pan_tompkins_qrs: 70 → 70 | KOD REPO |
| F7 | EEG (10Hz alfa) → wykryte 10.0Hz; oddech (~15/min=0.25Hz) → wykryte 0.253Hz | POTWIERDZONE | EEG 10,000 Hz, oddech 0,253 Hz | KOD REPO, demo eeg_normal/resp_normal |
| F8 | (stały cap 256 próbek) - dla EKG (fs=250Hz, n=15000) dawało to rozdzielczość ~1Hz | POTWIERDZONE | fs 250, n 15000, rozdzielczość 0,977 Hz |  |
| F9 | (~1.17Hz przy 70bpm) | POTWIERDZONE | z odstępów RR: 1,168 Hz = 70,1 bpm |  |
| F10 | `dominant_freq` błędnie wychodziło ~1.95Hz zamiast ~1.17Hz. Naprawiono podniesieniem górnego capu okna do 2048 próbek | POTWIERDZONE | nperseg=256: 1,953 Hz; obecnie (cap 2048): 2,319 Hz | NIEZALEŻNE (scipy.welch nperseg=256) |
| F11 | (EKG 0.5-40Hz, EEG 1-45Hz, oddech 0.05-1Hz; puls pomijany - zbyt niska częstotliwość próbkowania, fs=0.5Hz | POTWIERDZONE | FILTER_BAND_BY_TYPE: ecg 0,5–40, eeg 1–45, resp 0,05–1; brak pulse; demo puls fs 0,5 | KOD |
| F12 | (np. 20-60x, dobranym pod typ sygnału - inaczej demo pulsu trwałoby 10 minut) i co ~2 sekundy nowych danych | POTWIERDZONE | prędkość 20–60×, przeliczenie co 2 s, demo pulsu 600 s = 10 min | KOD |
| B1 | ### Bug 1 — `detect_peaks`: próg z MAD zawodzi przy rzadkich szczytach | POTWIERDZONE | detect_peaks: próg mediana + 3·std(x) | KOD |
| B2 | bo MAD jest zdominowany przez te ~95% próbek, które są szumem | POTWIERDZONE | szum = 95% próbek | konfiguracja z testu bug 1 |
| B3 | (amplituda szczytu 1.0, szum std=0.02) oryginalny próg `mediana + 1.5·MAD` wychodzi ≈ 0.024 | SPRZECZNE | mediana + 1,5·MAD = 0,0196 | konfiguracja z testu bug 1 (seed 1, n 500) |
| B4 | pojedyncza próbka szumu (`x[6]=0.0349`) była fałszywie wykrywana jako "szczyt" | SPRZECZNE | x[6] = -0,0107, powyżej starego progu, lokalne maksimum |  |
| B5 | próg zmieniony na `mediana + 3.0·std(x)` (≈0.33 w tym samym przykładzie | SPRZECZNE | mediana + 3·std = 0,658 |  |
| B6 | (indeksy `0` i `n-1` mogły wcześniej nigdy nie zostać wykryte jako szczyt) | POTWIERDZONE | obecnie wykryte 25/25 (w tym indeks 0) | stan po naprawie; stanu sprzed naprawy nie da się uruchomić z repo |
| B7 | ### Bug 2 — odrzucony kandydat: `rhythm()` bez filtra lokalnych maksimów | POTWIERDZONE | kandydat: wszystkie lagi ≥ progu, bez filtra lokalnych maksimów | KOD |
| B8 | detrend przez prostą linię `linspace(x[0], x[-1], n)` | POTWIERDZONE | candidate_user.py: detrend linspace | KOD |
| B9 | kandydat mimo to zgłaszał `power=0.656` (powyżej własnego progu 0.4) i aż 60 "wykrytych okresów" | SPRZECZNE | kopia z testu: power 0,684, 60 okresów; candidate_user.py: {'n_periods': 60, 'power': 0.6844332081879091} | konfiguracja z testu bug 2 (seed 0, max_lag 60) |
| B10 | daje poprawnie `power=0.0, periods=[]` | POTWIERDZONE | power 0.0, okresów 0 | KOD REPO |
| W1 | liczy drugą pochodną przez dwukrotne `np.gradient(x, t)`, co poprawnie obsługuje sygnały o nierównomiernym próbkowaniu w czasie (w przeciwieństwie do `np.diff(x, n=2)` | POTWIERDZONE | kandydat: 2× np.gradient; bio_core: np.gradient z t, np.diff(n=2) bez t | KOD |
| W2 | (0.05–0.06% w obu wariantach, 10 powtórzeń) | SPRZECZNE | z t 0,070%, bez t 0,020% (10 ziaren) | konfiguracja z testu twist |
| W3 | wyniki zgodne co do ~10 miejsc po przecinku (`0.00043334633260878435` vs `0.00043334633260879205`) | POTWIERDZONE | liczby w: ['README.md', 'docs/audit/claims_bio.py', 'docs/audit/recompute_bio.py'] |  |
| E1 | maksymalne |z| całego sygnału wynosiło tylko 1.21, dużo poniżej progu 3.5 | POTWIERDZONE | maks. |z| = 1,21; domyślny próg anomalies 3,5 | KOD REPO, demo resp_apnea |
| E2 | poprawnie wykryła okno 141.6s–178.0s, pokrywające się z wstrzykniętym epizodem bezdechu (150s–170s), bez fałszywych alarmów na normalnym oddechu | POTWIERDZONE | wykryte [[141.6, 178.0]] s; na resp_normal: 0 | KOD REPO; epizod 150–170 s z kodu |
| A1 | daje ~7-8% "fałszywych" anomalii | POTWIERDZONE | 7,8% próbek ecg_normal | KOD REPO |
| P1 | | EEG | 40 próbek | — | | oddech | 60 próbek | 10 s | | puls | 90 próbek | 60 s | | POTWIERDZONE | MAX_LAG eeg 40, resp 60, pulse 90; okno envelope resp 10 s, pulse 60 s | KOD (api.py i khipu_bio_alert.py) |
| K1 | wyłącznik `KHIPU_BOTTLENECK_ENABLED` (obecnie: WŁĄCZONY) | POTWIERDZONE | KHIPU_BOTTLENECK_ENABLED = True | R12 |
| K2 | (bpm rzędu dziesiątek, cv rzędu 0.01-0.3, moc rytmu w [-1,1]...) | SPRZECZNE | cv EKG 0,003–0,459; moc rytmu 0,000–0,995 | R11, wszystkie okna KHIPU 8 scenariuszy |
| K3 | Sprawdzone empirycznie na wszystkich 8 syntetycznych scenariuszach demo | POTWIERDZONE | 8 scenariuszy |  |
| K4 | | EKG | 10s / 2.5s | 0 | 2 | 2/2 | | EEG | 5s / 2.5s | 2 | 3 | 2/3 | | oddech | 30s / 7.5s | 1 | 4 | 1/4 | | puls | 120s / 15s | 3 | 1 | 1/1 | | POTWIERDZONE | ecg: fałszywe 0, alerty 2, trafione 2; eeg: fałszywe 2, alerty 3, trafione 2; resp: fałszywe 1, alerty 4, trafione 1; pulse: fałszywe 3, alerty 1, trafione 1 | R10 |
| K5 | `KHIPU_VALIDATED_TYPES = {"ecg", "eeg"}` | POTWIERDZONE | ['ecg', 'eeg'] | KOD |
| K6 | Domyślnie (`False`) wynik jest identyczny jak przed dodaniem tego modułu | SPRZECZNE | w kodzie KHIPU_BOTTLENECK_ENABLED = True | R12: nagłówek sekcji mówi „obecnie: WŁĄCZONY”, a to zdanie - że domyślnie False |
| K7 | Testy: 18 w `test_khipu_bio_alert.py` (moduł: kształt/determinizm/próg/ wyłącznik) + 4 w `test_api_khipu.py` | POTWIERDZONE | 18 + 4 |  |
| K8 | `/api/stream` woła go zawsze z `include_khipu=False` | POTWIERDZONE | /api/stream: include_khipu=False; test obecny i przechodzi | KOD |

## Reguły całego fragmentu

| Reguła | Wynik | Szczegóły |
| --- | --- | --- |
| R7b sformułowanie | DO ZŁAGODZENIA | „nigdy”: słowo bezwzględne |
| R7b sformułowanie | DO ZŁAGODZENIA | „nigdy”: słowo bezwzględne |
| R7b sformułowanie | DO ZŁAGODZENIA | „zawsze”: słowo bezwzględne |
| R7b sformułowanie | DO ZŁAGODZENIA | „nigdy”: słowo bezwzględne |

## Analiza (po uruchomieniu, post hoc — karty i reguły NIE zostały zmienione)

**Większość się zgadza.** 85/85 testów; brak plików danych (wszystko syntetyczne); filtr kauzalny, Pan-Tompkins
(70 → 18 vs 70 → 70), Welch dla EEG/oddechu, wykrycie bezdechu 141,6–178,0 s, ~7,8% „anomalii” na surowym EKG,
parametry i cała tabela walidacji KHIPU odtwarzają się co do liczby.

**Liczby w opisach błędów nie pochodzą z testów, na które README się powołuje.**
- Bug 1 (B3–B5): w konfiguracji `test_bug1_reprodukcja_oryginalnego_bledu_progu_mad` (seed 1, n 500) stary próg
  = 0,0196 (README: ≈0,024), nowy = 0,658 (README: ≈0,33), a `x[6]` = −0,0107 (README: 0,0349). Przeszukanie n ∈
  {500, 1000, 2000}, rr ∈ {20, 40, 50, 80, 100}, ziaren 0–49 nie znalazło konfiguracji z x[6] = 0,0349 — przykład z
  README nie jest odtwarzalny z repo. Wniosek (próg z MAD leży w paśmie szumu, próg ze std je oddziela) się utrzymuje.
  Uwaga: komunikat karty B4 („powyżej starego progu, lokalne maksimum”) był stałym tekstem — błąd karty; werdykt liczony
  poprawnie.
- Bug 2 (B9): w konfiguracji testu (seed 0) kandydat daje power 0,684, nie 0,656; 60 okresów się zgadza. 0,656 wychodzi
  dla ziaren 17 i 36. Wniosek się utrzymuje.
- twist (W2): w konfiguracji testu odsetek fałszywych alarmów to 0,070% z `t` i 0,020% bez `t` — oba niskie, ale różne
  ~3,5×, nie „0,05–0,06% w obu”.
- trend (W3): **błąd karty** — karta uznała liczby za odtwarzalne, bo znalazła je w plikach samego audytu. Właściwy
  werdykt: NIEROZSTRZYGNIĘTE (konfiguracji nie ma w repo).

**Welch dla EKG (F10) — naprawa nie działa na demo EKG.** Karta sprawdzała tylko stan „przed” (nperseg = 256 → 1,953 Hz)
i obecność capu 2048 — przeszła. Ale przy obecnym capie (nperseg = 2048) dominująca częstotliwość to 2,319 Hz
(2. harmoniczna, dalej od 1,168 Hz niż przed „naprawą”); przy 1024 — 1,221 Hz, przy 512 — 2,441 Hz. Test
`test_power_spectrum_okno_dostatecznie_duze_dla_ekg` sprawdza tylko `dominant_freq < 5 × prawdziwa`, więc przeszedłby
także przy 256. README mówi „Naprawiono”, a komentarz w `dsp.py` — że „przy nperseg>=1024 poprawnie”. Ograniczenie
opisane dalej w README (bpm z RR, nie z widma) jest właściwym wnioskiem.

**KHIPU.** K6: zdanie „Domyślnie (`False`)…” przeczy nagłówkowi „obecnie: WŁĄCZONY” i kodowi (`True`); komentarz w
`api.py` też mówi „Domyślnie WYŁĄCZONY”. K2: cv EKG w oknach wynosi 0,003–0,46 (README: 0,01–0,3) — różnica kosmetyczna
(dolna granica tuż poniżej progu R11 0,0033).

**R7b** — „nigdy”/„zawsze” opisują zachowanie kodu (np. `/api/stream` zawsze z `include_khipu=False`) i są prawdziwe.
