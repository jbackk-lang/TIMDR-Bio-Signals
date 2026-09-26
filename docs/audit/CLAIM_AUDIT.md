# Audyt twierdzeń: README → zastrzeżenie, testy, DSP, naprawione błędy, parametry, alert KHIPU (TIMDR-Bio-Signals)

Silnik: claim_audit v0.2 (TIMDR-AI-Core).

Drugi przebieg, po poprawkach README i komentarzy w kodzie (`CLAIM_AUDIT_ADDENDUM_1.md`). Pierwszy przebieg z analizą: `CLAIM_AUDIT_v1.md`. Karty zmieniono po pierwszym przebiegu — ten raport sprawdza zgodność poprawionego README z plikami, nie jest niezależnym testem.

Wygenerowano: 2026-09-26 12:34 UTC; reguły: `docs/audit/CLAIM_AUDIT_PREREG.md` (sha256 1d995093a9b1), karty: `claims_bio.py` (sha256 1915b6e75a6c), README sha256 bda322a6a682.

Werdykty kart: POTWIERDZONE 40, UJAWNIONE 1.

## Twierdzenia

| # | Twierdzenie (cytat z README) | Werdykt | Przeliczenie | Uwagi |
| --- | --- | --- | --- | --- |
| Z1 | Wszystkie dane demonstracyjne w tym repo są **w całości syntetyczne** (generowane matematycznie, `demo_scenarios.py`) — żadne prawdziwe dane pacjenta nie zostały użyte | POTWIERDZONE | pliki danych w repo: brak; demo z numpy.random | R13 |
| T1 | 85/85 testów przechodzi (`test_bio_core.py` + `test_demo_scenarios.py` + `test_dsp.py` + `test_khipu_bio_alert.py` + `test_api_khipu.py` | POTWIERDZONE | 85 testów w 7 plikach; ['85 passed in 4.94s'] | KOD REPO |
| F1 | przetwarzanie tego samego sygnału w jednym wywołaniu vs. w dwóch porcjach daje IDENTYCZNY wynik (różnica < 1e-9) | POTWIERDZONE | maks. różnica 0.0e+00 | konfiguracja z test_dsp.py |
| F2 | na granicy porcji powstaje widoczny skok (>0.01 różnicy amplitudy) | POTWIERDZONE | skok na granicy 1,204 | konfiguracja z test_dsp.py |
| F3 | Klasyczny algorytm (Pan & Tompkins, 1985): filtr 5-15Hz → pochodna → kwadrat → całkowanie w oknie ~150ms | POTWIERDZONE | docstring i kod pan_tompkins_qrs: 5-15 Hz, okno ~150 ms | KOD; rok publikacji jako DOKUMENT |
| F4 | wolnego dryfu linii bazowej (0.3Hz, amplituda porównywalna z QRS | POTWIERDZONE | dryf 0,3 Hz, amplituda 0,6 | konfiguracja z test_dsp.py |
| F5 | traci większość uderzeń: **70 → 18 wykrytych** | POTWIERDZONE | detect_peaks: 70 → 18 | KOD REPO |
| F6 | pozostaje w pełni stabilny: **70 → 70 wykrytych** (pasmo 5-15Hz usuwa dryf PRZED wykrywaniem szczytów) | POTWIERDZONE | pan_tompkins_qrs: 70 → 70 | KOD REPO |
| F7 | EEG (10Hz alfa) → wykryte 10.0Hz; oddech (~15/min=0.25Hz) → wykryte 0.253Hz | POTWIERDZONE | EEG 10,000 Hz, oddech 0,253 Hz | KOD REPO, demo eeg_normal/resp_normal |
| F8 | (stały cap 256 próbek) - dla EKG (fs=250Hz, n=15000) dawało to rozdzielczość ~1Hz | POTWIERDZONE | fs 250, n 15000, rozdzielczość 0,977 Hz |  |
| F9 | (~1.17Hz przy 70bpm) | POTWIERDZONE | z odstępów RR: 1,168 Hz = 70,1 bpm |  |
| F10 | Skutek: `dominant_freq` wychodziło ~1.95Hz zamiast ~1.17Hz | POTWIERDZONE | nperseg=256: 1,953 Hz; prawdziwa 1,168 Hz | NIEZALEŻNE + KOD REPO |
| F13 | Górny cap okna podniesiono do 2048 próbek, ale to NIE naprawia wyniku dla demo EKG: przy nperseg=2048 wychodzi ~2.32Hz (2. harmoniczna), przy 1024 ~1.22Hz, przy 512 ~2.44Hz | POTWIERDZONE | 256: 1,953 Hz; 512: 2,441 Hz; 1024: 1,221 Hz; 2048: 2,319 Hz | KOD REPO |
| F14 | Test sprawdza tylko, że wynik jest mniejszy niż 5× prawdziwa częstotliwość | POTWIERDZONE | test: dominant_freq < 5 × prawdziwa | KOD |
| F11 | (EKG 0.5-40Hz, EEG 1-45Hz, oddech 0.05-1Hz; puls pomijany - zbyt niska częstotliwość próbkowania, fs=0.5Hz | POTWIERDZONE | FILTER_BAND_BY_TYPE: ecg 0,5–40, eeg 1–45, resp 0,05–1; brak pulse; demo puls fs 0,5 | KOD |
| F12 | (np. 20-60x, dobranym pod typ sygnału - inaczej demo pulsu trwałoby 10 minut) i co ~2 sekundy nowych danych | POTWIERDZONE | prędkość 20–60×, przeliczenie co 2 s, demo pulsu 600 s = 10 min | KOD |
| B1 | ### Bug 1 — `detect_peaks`: próg z MAD zawodzi przy rzadkich szczytach | POTWIERDZONE | detect_peaks: próg mediana + 3·std(x) | KOD |
| B2 | bo MAD jest zdominowany przez te ~95% próbek, które są szumem | POTWIERDZONE | szum = 95% próbek | konfiguracja z testu bug 1 |
| B3 | (amplituda szczytu 1.0, szum std=0.02) oryginalny próg `mediana + 1.5·MAD` wychodzi ≈ 0.020 | POTWIERDZONE | mediana + 1,5·MAD = 0,0196 | konfiguracja z testu bug 1 |
| B4 | w tym sygnale 42 próbki szumu (lokalne maksima poza prawdziwymi szczytami) przekraczają stary próg | POTWIERDZONE | 42 lokalnych maksimów szumu powyżej starego progu |  |
| B5 | próg zmieniony na `mediana + 3.0·std(x)` (≈0.66 w tym samym przykładzie | POTWIERDZONE | mediana + 3·std = 0,658 |  |
| B6 | (indeksy `0` i `n-1` mogły wcześniej nigdy nie zostać wykryte jako szczyt) | POTWIERDZONE | obecnie wykryte 25/25 (w tym indeks 0) | stan po naprawie; stanu sprzed naprawy nie da się uruchomić z repo |
| B7 | ### Bug 2 — odrzucony kandydat: `rhythm()` bez filtra lokalnych maksimów | POTWIERDZONE | kandydat: wszystkie lagi ≥ progu, bez filtra lokalnych maksimów | KOD |
| B8 | detrend przez prostą linię `linspace(x[0], x[-1], n)` | POTWIERDZONE | candidate_user.py: detrend linspace | KOD |
| B9 | kandydat mimo to zgłaszał `power=0.684` (powyżej własnego progu 0.4) i aż 60 "wykrytych okresów" | POTWIERDZONE | power 0,684, 60 okresów | konfiguracja z testu bug 2 |
| B10 | daje poprawnie `power=0.0, periods=[]` | POTWIERDZONE | power 0.0, okresów 0 | KOD REPO |
| W1 | liczy drugą pochodną przez dwukrotne `np.gradient(x, t)`, co poprawnie obsługuje sygnały o nierównomiernym próbkowaniu w czasie (w przeciwieństwie do `np.diff(x, n=2)` | POTWIERDZONE | kandydat: 2× np.gradient; bio_core: np.gradient z t, np.diff(n=2) bez t | KOD |
| W2 | (0.07% z `t` i 0.02% bez `t`, 10 powtórzeń | POTWIERDZONE | z t 0,070%, bez t 0,020% | konfiguracja z testu twist |
| W3 | wyniki zgodne co do ~10 miejsc po przecinku (`0.00043334633260878435` vs `0.00043334633260879205`; jednorazowe sprawdzenie - konfiguracji tego porównania nie zapisano w repo) | UJAWNIONE | liczby tylko w: ['README.md'] | R9: brak konfiguracji w repo - README to teraz mówi |
| E1 | maksymalne |z| całego sygnału wynosiło tylko 1.21, dużo poniżej progu 3.5 | POTWIERDZONE | maks. |z| = 1,21; domyślny próg anomalies 3,5 | KOD REPO, demo resp_apnea |
| E2 | poprawnie wykryła okno 141.6s–178.0s, pokrywające się z wstrzykniętym epizodem bezdechu (150s–170s), bez fałszywych alarmów na normalnym oddechu | POTWIERDZONE | wykryte [[141.6, 178.0]] s; na resp_normal: 0 | KOD REPO; epizod 150–170 s z kodu |
| A1 | daje ~7-8% "fałszywych" anomalii | POTWIERDZONE | 7,8% próbek ecg_normal | KOD REPO |
| P1 | | EEG | 40 próbek | — | | oddech | 60 próbek | 10 s | | puls | 90 próbek | 60 s | | POTWIERDZONE | MAX_LAG eeg 40, resp 60, pulse 90; okno envelope resp 10 s, pulse 60 s | KOD (api.py i khipu_bio_alert.py) |
| K1 | wyłącznik `KHIPU_BOTTLENECK_ENABLED` (obecnie: WŁĄCZONY) | POTWIERDZONE | KHIPU_BOTTLENECK_ENABLED = True | R12 |
| K2 | (bpm rzędu dziesiątek, cv rzędu 0.003-0.5, moc rytmu w [-1,1]...) | POTWIERDZONE | cv EKG 0,003–0,459; moc rytmu 0,000–0,995 | R11 |
| K3 | Sprawdzone empirycznie na wszystkich 8 syntetycznych scenariuszach demo | POTWIERDZONE | 8 scenariuszy |  |
| K4 | | EKG | 10s / 2.5s | 0 | 2 | 2/2 | | EEG | 5s / 2.5s | 2 | 3 | 2/3 | | oddech | 30s / 7.5s | 1 | 4 | 1/4 | | puls | 120s / 15s | 3 | 1 | 1/1 | | POTWIERDZONE | ecg: fałszywe 0, alerty 2, trafione 2; eeg: fałszywe 2, alerty 3, trafione 2; resp: fałszywe 1, alerty 4, trafione 1; pulse: fałszywe 3, alerty 1, trafione 1 | R10 |
| K5 | `KHIPU_VALIDATED_TYPES = {"ecg", "eeg"}` | POTWIERDZONE | ['ecg', 'eeg'] | KOD |
| K6 | Po wyłączeniu (`False`) wynik jest identyczny jak przed dodaniem tego modułu | POTWIERDZONE | api.py liczy KHIPU tylko przy włączonej fladze; test przełącznika przechodzi | KOD |
| K7 | Testy: 18 w `test_khipu_bio_alert.py` (moduł: kształt/determinizm/próg/ wyłącznik) + 4 w `test_api_khipu.py` | POTWIERDZONE | 18 + 4 |  |
| K8 | `/api/stream` woła go zawsze z `include_khipu=False` | POTWIERDZONE | /api/stream: include_khipu=False; test obecny i przechodzi | KOD |

## Reguły całego fragmentu

| Reguła | Wynik | Szczegóły |
| --- | --- | --- |
| R7b sformułowanie | DO ZŁAGODZENIA | „nigdy”: słowo bezwzględne |
| R7b sformułowanie | DO ZŁAGODZENIA | „nigdy”: słowo bezwzględne |
| R7b sformułowanie | DO ZŁAGODZENIA | „zawsze”: słowo bezwzględne |
| R7b sformułowanie | DO ZŁAGODZENIA | „nigdy”: słowo bezwzględne |
