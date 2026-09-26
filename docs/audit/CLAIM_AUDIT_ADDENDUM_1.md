# Aneks 1 do CLAIM_AUDIT_PREREG.md (zapisany PRZED drugim uruchomieniem audytu)

Pierwszy przebieg: commit 5c17fa6, raport `CLAIM_AUDIT_v1.md` z analizą post hoc. Po nim:

1. README poprawione: liczby w opisach Bug 1, Bug 2 i `twist()` zastąpione wartościami z konfiguracji testów, na które
   README się powołuje (próg z MAD ≈ 0,020, 42 lokalne maksima szumu powyżej starego progu, próg ze std ≈ 0,66;
   power 0,684; 0,07% z `t` i 0,02% bez `t`); przy liczbach `trend()` dopisane, że konfiguracji nie zapisano; opis Welcha
   dla EKG — cap 2048 nie naprawia wyniku (2048 → 2,32 Hz, 1024 → 1,22 Hz, 512 → 2,44 Hz), test sprawdza tylko < 5×;
   cv 0,003–0,5; „Domyślnie (False)” → „Po wyłączeniu (False)”.
2. Komentarze w kodzie poprawione (bez zmian logiki): `api.py` (stan przełącznika KHIPU, bufor streamingu vs okno) i
   `dsp.py` (zależność dominującej częstotliwości EKG od nperseg).
3. `recompute_bio.py` v1.1: dodane `bug1.noise_local_max_above_old`, `welch.ecg_dominant_by_nperseg`; wyszukiwanie liczb
   `trend()` pomija `docs/audit/` (błąd karty W3 z przebiegu 1). Pozostałe sekcje przeliczone ponownie — bez zmian.
4. Karty v1.1 (`claims_bio.py`, lista w nagłówku), zmienione PO zobaczeniu wyników przebiegu 1 — drugi przebieg sprawdza
   zgodność poprawionego README z plikami, nie jest niezależnym testem.
