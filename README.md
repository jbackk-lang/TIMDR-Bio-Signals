# TIMDR-Bio-Signals

TIMDR zastosowane do sygnałów fizjologicznych: **EKG, EEG, puls, oddech**.
Wykrywa: arytmie/nieregularność rytmu, anomalie impulsów, nagłe zmiany
(twist), powolne dryfy (trend) oraz — dodatkowo — zaniki oscylacji
(np. bezdech).

## ⚠️ Zastrzeżenie — bardzo ważne

**To NIE jest wyrób medyczny.** TIMDR-Bio-Signals jest narzędziem
badawczo-edukacyjnym do eksperymentowania z analizą statystyczną
sygnałów czasowych. Nie diagnozuje żadnej choroby, nie zastępuje
lekarza, pielęgniarki, ratownika ani certyfikowanego sprzętu medycznego
(Holter EKG, pulsoksymetr klasy medycznej, EEG kliniczne itd.).

Wszystkie dane demonstracyjne w tym repo są **w całości syntetyczne**
(generowane matematycznie, `demo_scenarios.py`) — żadne prawdziwe dane
pacjenta nie zostały użyte. Wyniki analizy to **statystyczne odchylenia
względem lokalnej historii danego sygnału**, a nie rozpoznania
kliniczne. Jeśli martwisz się o swoje zdrowie lub kogoś bliskiego,
skontaktuj się z lekarzem lub odpowiednimi służbami medycznymi — nie
z tym narzędziem.

## Szybki start

```
run.bat
```

Zainstaluje zależności (`flask`, `numpy`, `pytest`), uruchomi testy i
otworzy dashboard pod `http://127.0.0.1:5050`.

## Struktura

- `bio_core.py` — silnik: `TIMDRBioSignal` (anomalie, rytm, twist,
  trend, wykrywanie szczytów, spadki obwiedni) + `TIMDRBioFusion`
  (fuzja wielokanałowa).
- `demo_scenarios.py` — 8 syntetycznych scenariuszy demo (EKG
  normalne/arytmia, EEG normalne/napadopodobne, puls
  normalny/tachykardia, oddech normalny/bezdech).
- `demo.py` — uruchamia wszystkie scenariusze w konsoli.
- `api.py` — Flask, port 5050: `/`, `/api/health`, `/api/scenarios`,
  `/api/demo?scenario=...`, `POST /api/analyze` (własny sygnał).
- `static/dashboard.html` — panel: wybór scenariusza, karty z
  wynikami, wykres sygnału z zaznaczonymi szczytami/anomaliami/
  zakresami spadku obwiedni.
- `test_bio_core.py`, `test_demo_scenarios.py` — 33 testy (pytest).
- `candidate_user.py` — kod klasy `TIMDRBio` nadesłany do wglądu w
  trakcie budowy tego repo, zachowany wyłącznie do testów
  porównawczych (patrz "Kod nadesłany do wglądu" niżej). **Nie jest
  używany przez `api.py` / `demo.py`.**

## Endpointy API

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/` | dashboard |
| GET | `/api/health` | healthcheck + zastrzeżenie |
| GET | `/api/scenarios` | lista scenariuszy demo |
| GET | `/api/demo?scenario=ecg_normal` | analiza scenariusza demo |
| POST | `/api/analyze` | analiza własnego sygnału: `{signal_type, fs, values}` |

## Testy

```
python -m pytest -q
```

33/33 testów przechodzi (`test_bio_core.py` + `test_demo_scenarios.py`).

## Znalezione i naprawione błędy

### Bug 1 — `detect_peaks`: próg z MAD zawodzi przy rzadkich szczytach

**Objaw:** przy sygnale, gdzie prawdziwe szczyty (np. zespoły QRS w
EKG) stanowią mały procent wszystkich próbek, próg oparty o medianę
odchyleń bezwzględnych (MAD) wypada niemal w paśmie samego szumu tła —
bo MAD jest zdominowany przez te ~95% próbek, które są szumem, a nie
szczytem.

**Dowód (reprodukcja w `test_bug1_reprodukcja_oryginalnego_bledu_progu_mad`):**
dla regularnego sygnału EKG-podobnego (amplituda szczytu 1.0, szum
std=0.02) oryginalny próg `mediana + 1.5·MAD` wychodzi ≈ 0.024 — czyli
praktycznie w paśmie szumu. Skutek: pojedyncza próbka szumu
(`x[6]=0.0349`) była fałszywie wykrywana jako "szczyt".

**Naprawa:** próg zmieniony na `mediana + 3.0·std(x)` (≈0.33 w tym
samym przykładzie — wyraźnie oddziela szum od prawdziwych szczytów).
Dodatkowo naprawiono wykluczanie brzegów sygnału (indeksy `0` i `n-1`
mogły wcześniej nigdy nie zostać wykryte jako szczyt).

### Bug 2 — odrzucony kandydat: `rhythm()` bez filtra lokalnych maksimów

W trakcie budowy tego repo otrzymałem od użytkownika gotową
implementację klasy `TIMDRBio` (zachowaną w `candidate_user.py`).
Zamiast przyjąć ją bezkrytycznie, przetestowałem ją empirycznie obok
własnej wersji.

**Problem w wersji `rhythm()` z tego kandydata:** detrend przez prostą
linię `linspace(x[0], x[-1], n)` (zamiast pełnego dopasowania trendu) i
— co ważniejsze — zgłaszanie periodyczności dla **każdego** opóźnienia
(lag) autokorelacji powyżej progu, zamiast tylko dla lokalnych maksimów
funkcji autokorelacji.

**Dowód (`test_bug2_reprodukcja_odrzuconego_kandydata_rhythm`):** na
sygnale celowo **nieregularnym** (arytmicznym — bez prawdziwego
rytmu) kandydat mimo to zgłaszał `power=0.656` (powyżej własnego progu
0.4) i aż 60 "wykrytych okresów". To dyskwalifikujący błąd dla
wykrywacza arytmii — sygnał arytmiczny musi dawać *niską* moc rytmu,
nie wysoką.

**Weryfikacja własnej implementacji na tym samym sygnale:** pełny
detrend (`np.polyfit`) + filtr tylko lokalnych maksimów autokorelacji
daje poprawnie `power=0.0, periods=[]`.

**Decyzja:** zachowana została moja wcześniej zweryfikowana wersja
`rhythm()` (pełny detrend + tylko lokalne maksima).

### Częściowo przyjęte z kodu nadesłanego do wglądu — `twist()` z jawnym `t`

Wersja `twist()` z `candidate_user.py` liczy drugą pochodną przez
dwukrotne `np.gradient(x, t)`, co poprawnie obsługuje sygnały o
nierównomiernym próbkowaniu w czasie (w przeciwieństwie do
`np.diff(x, n=2)`, który zakłada stały krok). Zweryfikowane
empirycznie: porównywalny, niski odsetek fałszywych alarmów na czystym
szumie (0.05–0.06% w obu wariantach, 10 powtórzeń). **Przyjęte:**
`twist()` w `bio_core.py` przyjmuje teraz opcjonalny parametr `t`; gdy
podany, używa `np.gradient`, w przeciwnym razie działa jak dotychczas.

`trend()` z kodu nadesłanego do wglądu została zweryfikowana liczbowo
względem mojej wersji na syntetycznym sygnale ze znacznikami czasu w
skali epoki Unix — wyniki zgodne co do ~10 miejsc po przecinku
(`0.00043334633260878435` vs `0.00043334633260879205`). Zachowana
została moja wersja (liczy nachylenie tylko dla ostatniego okna, zgodnie
z konwencją API używaną w innych modułach TIMDR w tym zestawie repo).

### Nowa funkcja — `envelope_drop()`: wykrywanie zaniku oscylacji (np. bezdech)

**Problem:** sygnał oddechowy naturalnie oscyluje wokół zera co cykl
oddechowy — więc "spłaszczony" fragment (np. bezdech: brak ruchu,
wartości bliskie zeru) jest punktowo (próbka po próbce) statystycznie
nieodróżnialny od normalnych próbek w trakcie oscylacji. Punktowe
metody (`anomalies`, `twist`) fundamentalnie nie potrafią tego wykryć —
potwierdzone empirycznie: na scenariuszu `resp_apnea` maksymalne |z|
całego sygnału wynosiło tylko 1.21, dużo poniżej progu 3.5.

**Rozwiązanie:** nowa metoda `envelope_drop(x, window, factor)` liczy
przesuwane okna odchylenia standardowego, a następnie MAD-z na tej
serii lokalnych odchyleń — wykrywając **spadek** zmienności (nie
wartości). Zweryfikowana na scenariuszu `resp_apnea`: poprawnie
wykryła okno 141.6s–178.0s, pokrywające się z wstrzykniętym epizodem
bezdechu (150s–170s), bez fałszywych alarmów na normalnym oddechu.

### Ograniczenie udokumentowane — `anomalies()` na surowym EKG

Zastosowanie `anomalies()` (MAD-z) bezpośrednio na surowym przebiegu
EKG daje ~7-8% "fałszywych" anomalii — bo każdy zespół QRS jest
oczekiwaną, normalną, dużą odchyłką od linii bazowej. **Właściwe
zastosowanie dla sygnałów spiczasto-okresowych (jak EKG):** wywołać
`anomalies()` na **wyekstrahowanych amplitudach poszczególnych uderzeń**
(`x[peaks]`), nie na surowym przebiegu — czyli pytać "czy to jedno
uderzenie jest nietypowe względem innych uderzeń", a nie "czy ta
próbka napięcia jest nietypowa względem linii bazowej". Zaimplementowane
w `demo.py` i `api.py` (`beat_amplitude_anomalies`). Udokumentowane
też w docstringu `anomalies()` w `bio_core.py`.

## Rekomendowane parametry per typ sygnału

| Sygnał | max_lag (rhythm) | okno envelope_drop |
|---|---|---|
| EEG | 40 próbek | — |
| oddech | 60 próbek | 10 s |
| puls | 90 próbek | 60 s |
| EKG | (analiza per-uderzenie, nie surowy rhythm) | — |

`rhythm()` powinien być liczony **per kanał**, nigdy na sygnale po
fuzji wielokanałowej (`TIMDRBioFusion.fuse`) — różne sygnały
fizjologiczne mają różne częstotliwości charakterystyczne, a łączenie
ich przed analizą rytmu grozi dokładnie tym samym artefaktem
"wyprostowania" (rectification), który jest udokumentowany jako
powtarzający się błąd w innych modułach TIMDR tego zestawu repo.
