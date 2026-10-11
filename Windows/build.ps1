$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno. Instala Python 3.11 o superior.' }
}
& $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt') 'pyinstaller==6.16.0'
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias de compilación.' }
$resourcesPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'Resources'
& $pythonPath -m PyInstaller --noconfirm --clean --onefile --windowed --name Blablabla `
    --icon (Join-Path $PSScriptRoot 'Blablabla.ico') `
    --distpath (Join-Path $PSScriptRoot 'dist') --workpath (Join-Path $PSScriptRoot 'build') `
    --specpath $PSScriptRoot --exclude-module tkinter `
    --add-data "$resourcesPath;Resources" (Join-Path $PSScriptRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el ejecutable.' }
Write-Host "Ejecutable: $PSScriptRoot\dist\Blablabla.exe"
