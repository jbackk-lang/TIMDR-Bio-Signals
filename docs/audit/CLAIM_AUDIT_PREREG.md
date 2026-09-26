# Audyt twierdzeń README — TIMDR-Bio-Signals — pre-rejestracja

Status: ZAMROŻONE i zacommitowane PRZED pierwszym uruchomieniem `recompute_bio.py` i audytu. Silnik: `tools/claim_audit.py`
(TIMDR-AI-Core `claim_audit` v0.2), reguły ogólne R1–R7 jak w `TIMDR-AI-Core/CLAIM_AUDIT.md`. Audytor przeczytał README,
testy, `bio_core.py`, `dsp.py`, `api.py`, `demo_scenarios.py`, `khipu_bio_alert.py` przed napisaniem kart; liczb z README
nie przeliczał. Wszystkie dane repo są syntetyczne — audyt sprawdza zgodność README z kodem, nie jakość na danych klinicznych.

## Zakres
README.md: „## ⚠️ Zastrzeżenie” do „## Szybki start”; „## Testy” do końca pliku. „Szybki start”, „Struktura”, „Endpointy”
poza zakresem.

## Poziomy dowodu
KOD REPO (wywołanie funkcji repozytorium w konfiguracji z testu lub z demo), NIEZALEŻNE (własne przeliczenie, np. Welch
z nperseg=256 przez scipy), KOD (odczyt stałych/fragmentów źródła), DOKUMENT (bibliografia/zapis bez przeliczenia).

## Reguły dodatkowe
- R8 Liczby z testów: przeliczane w tej samej konfiguracji co test (ziarno, n, sygnał demo); zgodność do pokazanej
  precyzji; „≈”/„~” = ±15%.
- R9 Liczby, dla których repozytorium nie zawiera konfiguracji (skryptu/testu) pozwalającej je odtworzyć, dostają
  NIEROZSTRZYGNIĘTE.
- R10 Tabela KHIPU: alert „trafia”, gdy jego czas `t_s` leży w [początek − 5 s, koniec + 5 s] wstrzykniętego epizodu.
  Epizody z kodu `demo_scenarios.py`: EKG `irregular_window_s`, EEG 13,5–17,5 s, puls 240–360 s, oddech 150–170 s.
  Fałszywe alarmy = liczba alertów na scenariuszu `*_normal`. Okna/kroki z `WINDOW_S_BY_TYPE`/`STEP_S_BY_TYPE`.
  POTWIERDZONE tylko, gdy zgadzają się wszystkie komórki.
- R11 „rzędu a–b”: obserwowany zakres (po wszystkich oknach KHIPU ośmiu scenariuszy) mieści się w [a/3, 3b].
- R12 Stan przełącznika: „obecnie”/„domyślnie” = wartość `KHIPU_BOTTLENECK_ENABLED` w `khipu_bio_alert.py`.
- R13 „w całości syntetyczne”: brak plików danych (csv, npz, npy, edf, dat, mat, h5, wav, hea) w repozytorium, a
  scenariusze demo generowane przez `numpy.random`.
