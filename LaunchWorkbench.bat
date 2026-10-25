@echo off
setlocal
set "QW_PYTHON=%~dp0quant_workbench\.venv\Scripts\pythonw.exe"
if not exist "%QW_PYTHON%" (
    echo Python environment missing. See quant_workbench README.md.
    pause
    exit /b 1
)
start "" "%QW_PYTHON%" "%~dp0quant_workbench\launch.pyw"
