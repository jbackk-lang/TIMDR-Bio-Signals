@echo off
setlocal
echo ============================================================
echo  TIMDR-Bio-Signals - lokalne API + dashboard
echo  UWAGA: to NIE jest wyrob medyczny. Narzedzie badawczo-
echo  -edukacyjne. Patrz README.md.
echo ============================================================
echo.
echo Instalacja/aktualizacja zaleznosci...
pip install --quiet flask numpy pytest
if errorlevel 1 (
    echo BLAD: nie udalo sie zainstalowac zaleznosci pip.
    pause
    exit /b 1
)

echo.
echo Uruchamiam testy (pytest)...
python -m pytest -q
if errorlevel 1 (
    echo.
    echo UWAGA: co najmniej jeden test nie przeszedl. Serwer uruchomi
    echo sie mimo to, ale sprawdz powyzsze wyniki testow.
    echo.
)

echo.
echo Start serwera na http://127.0.0.1:5050
echo (Ctrl+C aby zatrzymac)
echo.
start "" http://127.0.0.1:5050
python api.py

pause
