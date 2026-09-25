@echo off
REM Construction complete : executable PyInstaller puis installateur Inno Setup.
REM Prerequis : Python 3.11+, et Inno Setup 6 dans le PATH (iscc.exe).

setlocal
cd /d "%~dp0"

echo [1/5] Environnement virtuel...
if not exist .venv (
    python -m venv .venv || goto :erreur
)
call .venv\Scripts\activate.bat

echo [2/5] Dependances...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet || goto :erreur
python -m pip install pyinstaller --quiet || goto :erreur

echo [3/5] Compilation des traductions...
python translations\build_translations.py release || goto :erreur

echo [4/5] Compilation de l'executable...
rmdir /s /q dist 2>nul
pyinstaller build\Glaneur.spec --noconfirm --clean || goto :erreur

echo [5/5] Creation de l'installateur...
where iscc >nul 2>nul
if errorlevel 1 (
    echo    Inno Setup introuvable dans le PATH, etape ignoree.
    echo    L'executable est disponible dans dist\Glaneur\
    goto :fin
)
iscc build\installer.iss || goto :erreur
echo    Installateur : build\Output\

:fin
echo.
echo Termine.
exit /b 0

:erreur
echo.
echo ECHEC de la construction.
exit /b 1
