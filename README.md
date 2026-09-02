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
- `dsp.py` — filtracja Butterwortha (offline zerofazowa + kauzalna
  strumieniowa), detektor QRS Pan-Tompkins, widmo mocy metodą Welcha.
  Patrz sekcja "Nowe funkcje DSP" niżej.
- `demo_scenarios.py` — 8 syntetycznych scenariuszy demo (EKG
  normalne/arytmia, EEG normalne/napadopodobne, puls
  normalny/tachykardia, oddech normalny/bezdech).
- `demo.py` — uruchamia wszystkie scenariusze w konsoli.
- `api.py` — Flask, port 5050: `/`, `/api/health`, `/api/scenarios`,
  `/api/demo?scenario=...`, `POST /api/analyze` (własny sygnał),
  eksport JSON/CSV, streaming SSE (`/api/stream`).
- `static/dashboard.html` — panel: wybór scenariusza, przełącznik
  filtra Butterwortha, przyciski eksportu, tryb "na żywo" (symulacja
  streamingu), karty z wynikami, wykres sygnału, wykres widma mocy.
- `test_bio_core.py`, `test_demo_scenarios.py`, `test_dsp.py` — 50
  testów (pytest).
- `bio_trigger.py` — **czujnik sygnałowy** (NIE model, NIE rozpoznanie
  kliniczne): `BioTrigger`, dispatcher nad wynikiem `analyze_signal()` —
  jeden, priorytetyzowany wynik "co jest najważniejsze i gdzie" nad
  wszystkimi równoległymi polami (anomalie/twist/spadek obwiedni/
  arytmia/anomalia amplitudy uderzenia), zamiast osobnych list bez
  wspólnej hierarchii. Priorytet: `ENVELOPE_DROP` (utrata zmienności —
  bezdech/asystolia/cisza EEG) > `ARRHYTHMIA` (tylko EKG) >
  `BEAT_ANOMALY` (tylko EKG) > `TWIST` > `ANOMALY` > `NONE`. Wpięty do
  `api.py::analyze_signal()` (pole `"trigger"` w każdej odpowiedzi -
  `/api/analyze`, `/api/demo`, eksport, streaming). Testy:
  `test_bio_trigger.py` (logika dispatchera) + `test_bio_trigger_api.py`
  (wpięcie, m.in. `resp_apnea` → `envelope_drop`, `ecg_arrhythmia` →
  `arrhythmia`, `ecg_normal` → `none`) — 84/84 testów łącznie.
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
| GET | `/api/demo?scenario=ecg_normal&filter=1` | analiza scenariusza demo (opcjonalny filtr pasmowoprzepustowy) |
| POST | `/api/analyze` | analiza własnego sygnału: `{signal_type, fs, values, filter}` |
| GET | `/api/export/demo?scenario=...&format=csv\|json` | eksport wyniku analizy scenariusza demo do pliku |
| POST | `/api/export/analyze` | eksport analizy własnego sygnału do pliku (`{..., format}`) |
| GET | `/api/stream?scenario=...&speed=20` | symulowany strumień "na żywo" (Server-Sent Events) |

## Testy

```
python -m pytest -q
```

84/84 testów przechodzi (`test_bio_core.py` + `test_demo_scenarios.py` +
`test_dsp.py` + `test_khipu_bio_alert.py` + `test_api_khipu.py` - dwa
ostatnie dotyczą opcjonalnego alertu KHIPU, patrz sekcja niżej - +
`test_bio_trigger.py` + `test_bio_trigger_api.py`, patrz "Struktura"
wyżej).

## Nowe funkcje DSP (`dsp.py`)

### Filtracja pasmowoprzepustowa Butterwortha

Dwie implementacje, do dwóch różnych zastosowań:

- `butter_bandpass_filter(x, fs, low, high, order)` — **offline,
  zerofazowa** (`scipy.signal.filtfilt`) - filtruje w przód i w tył,
  więc wynik nie ma przesunięcia czasowego względem oryginału. Wymaga
  całego sygnału na raz - **nie nadaje się do przetwarzania na żywo**
  (musiałaby "znać przyszłość"). Używana w dashboardzie (przełącznik
  "filtr pasmowoprzepustowy") i wewnętrznie przez `pan_tompkins_qrs()`.
- `CausalBandpassFilter` — **kauzalna**, z utrzymywanym stanem
  (`scipy.signal.lfilter` + `zi`) między kolejnymi wywołaniami
  `process()`. Używana przez `/api/stream` do przetwarzania danych
  napływających porcjami. Zweryfikowano empirycznie
  (`test_dsp.py::test_causal_filter_stan_ciagly_miedzy_porcjami`):
  przetwarzanie tego samego sygnału w jednym wywołaniu vs. w dwóch
  porcjach daje IDENTYCZNY wynik (różnica < 1e-9), o ile stan jest
  zachowany - a bez zachowania stanu (`test_causal_filter_bez_stanu_dawalby_skok_na_granicy`)
  na granicy porcji powstaje widoczny skok (>0.01 różnicy amplitudy).

**Filtracja offline vs strumieniowa - dlaczego to ważne:** offline
(`filtfilt`) daje "ładniejszy" wynik (zero przesunięcia fazowego), ale
tylko dla danych, które już w całości mamy. Dla prawdziwego streamingu
(dane przychodzą próbka-po-próbce/porcja-po-porcji) trzeba użyć wersji
kauzalnej, która wprowadza niewielkie, ale nieuniknione opóźnienie
fazowe - to fundamentalne ograniczenie fizyczne (kauzalny filtr nie
może "zobaczyć" próbek, które jeszcze nie nadeszły), nie błąd
implementacji.

### Detektor QRS Pan-Tompkins (`pan_tompkins_qrs`)

Klasyczny algorytm (Pan & Tompkins, 1985): filtr 5-15Hz → pochodna →
kwadrat → całkowanie w oknie ~150ms → adaptacyjny próg z okresem
refrakcji → mapowanie z powrotem na szczyty oryginalnego sygnału.

**Dlaczego to ulepszenie, nie tylko alternatywa dla `detect_peaks()`:**
zweryfikowano empirycznie (`test_dsp.py::test_pan_tompkins_odporny_na_dryf_liniowy_bazowej`),
że po dodaniu do czystego demo EKG realistycznego, wolnego dryfu linii
bazowej (0.3Hz, amplituda porównywalna z QRS - typowe dla ruchu
pacjenta/oddychania przy realnym EKG):

- `detect_peaks()` (prosty próg oparty o globalne `std(x)`) traci
  większość uderzeń: **70 → 18 wykrytych** (próg rozregulowany przez
  dryf).
- `pan_tompkins_qrs()` pozostaje w pełni stabilny: **70 → 70
  wykrytych** (pasmo 5-15Hz usuwa dryf PRZED wykrywaniem szczytów).

`api.py`/`demo.py` używają teraz `pan_tompkins_qrs()` jako domyślnej
metody wykrywania załamków R dla EKG (`detect_peaks()` pozostaje w
`bio_core.py` jako ogólny detektor szczytów dla innych zastosowań, np.
cykli oddechowych).

### Widmo mocy (`power_spectrum`, metoda Welcha)

Zwraca częstotliwości, moc oraz częstotliwość/moc dominującą. Metoda
Welcha (nakładające się okna, uśrednianie) zamiast surowego
periodogramu - dużo mniej szumu wariancji.

**Zweryfikowano poprawność na sygnałach o znanej częstotliwości:**
EEG (10Hz alfa) → wykryte 10.0Hz; oddech (~15/min=0.25Hz) → wykryte
0.253Hz.

**Znaleziony i naprawiony błąd:** domyślny rozmiar okna Welcha był
zbyt mały (stały cap 256 próbek) - dla EKG (fs=250Hz, n=15000) dawało
to rozdzielczość ~1Hz, za grubą, by odróżnić częstotliwość
fundamentalną (~1.17Hz przy 70bpm) od jej najbliższej harmonicznej.
Skutek: `dominant_freq` błędnie wychodziło ~1.95Hz zamiast ~1.17Hz.
Naprawiono podniesieniem górnego capu okna do 2048 próbek.

**Udokumentowane ograniczenie (nie błąd):** nawet z poprawionym
oknem, dla **surowego przebiegu EKG** (kształt impulsowy zespołów QRS)
`dominant_freq` bywa niedokładne (moc widma rozkłada się na kilka
bliskich harmonicznych zamiast jednego ostrego szczytu na
częstotliwości fundamentalnej - to naturalna cecha widma sygnałów
impulsowych, nie artefakt implementacji). Dlatego `api.py` zwraca dla
EKG `spectrum` tylko informacyjnie, z jawną notatką
(`spectrum_note`) kierującą do pola `bpm` (liczonego z odstępów RR
przez `pan_tompkins_qrs` + `rhythm_regularity`) jako właściwego źródła
częstotliwości rytmu serca. Dla EEG/oddechu (sygnały gładkie,
oscylacyjne) `power_spectrum()` działa dokładnie i jest głównym
źródłem informacji o częstotliwości.

## Filtr, eksport, streaming - jak używać

- **Filtr:** zaznacz "filtr pasmowoprzepustowy (Butterworth)" w
  dashboardzie przed analizą scenariusza - pasmo dobierane
  automatycznie pod typ sygnału (EKG 0.5-40Hz, EEG 1-45Hz, oddech
  0.05-1Hz; puls pomijany - zbyt niska częstotliwość próbkowania,
  fs=0.5Hz, na sensowną filtrację pasmowoprzepustową).
- **Eksport:** przyciski "CSV"/"JSON" pobierają bieżący scenariusz
  (z uwzględnieniem stanu przełącznika filtra) jako plik. CSV zawiera
  tabelę czas/wartość/[przefiltrowane]/znaczniki (szczyty/anomalie);
  JSON zawiera pełny wynik analizy wraz z metadanymi (bpm, moc rytmu
  itd.).
- **Na żywo:** przycisk "📡 Symuluj na żywo" otwiera połączenie SSE
  (`/api/stream`), które odtwarza gotowy sygnał demo z przyspieszeniem
  czasowym (np. 20-60x, dobranym pod typ sygnału - inaczej demo pulsu
  trwałoby 10 minut) i co ~2 sekundy nowych danych przelicza pełną
  analizę na **ostatnim oknie** (nie całej historii - tak jak
  prawdziwy monitor). To symulacja do celów demonstracyjnych, NIE
  prawdziwa akwizycja z urządzenia.

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

## Alert KHIPU (`khipu_bio_alert.py`) — opcjonalny, wyłącznik `KHIPU_BOTTLENECK_ENABLED` (obecnie: WŁĄCZONY)

Cała reszta tego repo analizuje **jedną cechę sygnału naraz** (rytm,
anomalie, twist, obwiednia...) - świadomy wybór projektowy (patrz wyżej).
`khipu_bio_alert.py` robi coś węższego i dodatkowego: bierze KILKA już
policzonych cech okna naraz, ściska je w jeden DYSKRETNY "odcisk stanu"
(`State9Bottleneck` z [jbackk-lang/KHIPU-NEURAL](../KHIPU-NEURAL), wierny
port matematyki - ten sam mechanizm co w `analizator-gieldowy-v3`) i
porównuje odcisk sąsiednich okien czasu. Spadek zgodności = kilka cech
zmieniło się jednocześnie - potencjalnie widoczne wcześniej/wyraźniej niż
w którymkolwiek pojedynczym detektorze osobno. **To jest DODATKOWY,
KOMPLEMENTARNY alert - nie zastępuje, nie podnosi ani nie obniża
wiarygodności żadnego z istniejących wyników.**

Różnica względem `analizator-gieldowy-v3/khipu_bottleneck.py`: **brak
`calibrate()`/treningu.** Tam kalibracja miała jawnie-heurystyczną
etykietę "ta sama faza" ze znaku FLOW. Tu nie ma analogicznie
uzasadnionej etykiety "ten sam stan fizjologiczny" - wymyślanie jednej
tylko po to, by było czym trenować, byłoby mniej uczciwe niż jej brak.
Projekcja jest więc wyłącznie deterministycznym, NIEtrenowanym "twardym
filtrem" (ten sam wzorzec Walsha-Hadamarda co w wersji giełdowej). Cechy
wejściowe są z-score'owane (MAD-z, ten sam `_mad_z` co reszta
`bio_core.py`) kolumna po kolumnie, po wszystkich oknach danego
nagrania, zanim trafią do projekcji - bo mają bardzo różne surowe skale
(bpm rzędu dziesiątek, cv rzędu 0.01-0.3, moc rytmu w [-1,1]...).

### Walidacja na `demo_scenarios.py` — wynik NIEJEDNOLITY, przeczytaj przed włączeniem

Sprawdzone empirycznie na wszystkich 8 syntetycznych scenariuszach demo:
alerty na scenariuszu `*_normal` (fałszywe alarmy - ma ich NIE być) oraz
trafienie alertu w okolicy (±5s) znanego, wstrzykniętego epizodu w
scenariuszu nieprawidłowym.

| Sygnał | okno/krok | fałszywe alarmy (`*_normal`) | alerty na scenariuszu z epizodem | trafienie w oknie epizodu |
|---|---|---|---|---|
| EKG | 10s / 2.5s | 0 | 2 | 2/2 |
| EEG | 5s / 2.5s | 2 | 3 | 2/3 |
| oddech | 30s / 7.5s | 1 | 4 | 1/4 |
| puls | 120s / 15s | 3 | 1 | 1/1 |

**Wniosek: EKG i EEG dają rozsądny wynik (zero/mało fałszywych alarmów,
trafienie w epizod) - oddech i puls NIE (zbyt mało okien w typowym
nagraniu na stabilny z-score kolumn, dyskryminacja słaba).**
`KHIPU_VALIDATED_TYPES = {"ecg", "eeg"}` w `khipu_bio_alert.py` koduje
dokładnie tę granicę - wynik API/dashboardu ma pole
`khipu_regime_validated` (`False` dla oddechu/pulsu), żeby to ograniczenie
było widoczne w interfejsie, nie tylko w kodzie źródłowym. Progi
okna/kroku są USTALONE RĘCZNIE na podstawie tej jednej, w pełni
syntetycznej walidacji - nie skalibrowane na żadnych realnych danych,
punkt startowy do dalszego dostrojenia, nie potwierdzona liczba.

Co robi, gdy włączony (`KHIPU_BOTTLENECK_ENABLED = True`): `api.py`
dopisuje do wyniku `/api/demo` i `/api/analyze` (nie do `/api/stream` -
nie jest jeszcze wpięty w tryb "na żywo") pola `khipu_regime_last`,
`khipu_regime_mean`, `khipu_regime_alerts` (komunikaty),
`khipu_regime_alerts_idx` (indeksy próbek - naniesione na wykres
fioletowymi znacznikami w dashboardzie), `n_khipu_regime_alerts`,
`khipu_regime_alert_active`, `khipu_regime_validated`. Domyślnie
(`False`) wynik jest identyczny jak przed dodaniem tego modułu.

Testy: 18 w `test_khipu_bio_alert.py` (moduł: kształt/determinizm/próg/
wyłącznik) + 3 w `test_api_khipu.py` (integracja z `api.py`, wyłącznik w
obie strony, `khipu_regime_validated`) - patrz sekcja "Testy" na górze
pliku dla łącznej liczby testów całego repo.
