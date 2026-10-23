@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale Python 3.9 ou superior e habilite Add Python to PATH.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    py -m venv .venv
    if errorlevel 1 goto erro
)

echo Instalando ou atualizando dependencias...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto erro

echo.
echo Abra http://127.0.0.1:5000 no navegador.
echo Mantenha esta janela aberta enquanto utilizar o sistema.
echo.
.venv\Scripts\python.exe main.py
goto fim

:erro
echo Ocorreu um erro ao preparar o sistema.
pause
:fim
endlocal
