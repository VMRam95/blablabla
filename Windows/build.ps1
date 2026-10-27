$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno. Instala Python 3.11 o superior.' }
}
& $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt') 'pyinstaller==6.16.0'
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias de compilación.' }
$resourcesPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'Resources'
$buildPath = Join-Path $PSScriptRoot 'build'
# A folder build starts instantly; --onefile unpacked ~50 MB on every launch.
& $pythonPath -m PyInstaller --noconfirm --clean --onedir --windowed --name Blablabla `
    --icon (Join-Path $PSScriptRoot 'Blablabla.ico') `
    --distpath (Join-Path $buildPath 'onedir') --workpath $buildPath `
    --specpath $PSScriptRoot --exclude-module tkinter `
    --add-data "$resourcesPath;Resources" (Join-Path $PSScriptRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el ejecutable.' }
# Keep dist\Blablabla.exe at the same path so existing shortcuts keep working.
$distPath = Join-Path $PSScriptRoot 'dist'
New-Item -ItemType Directory -Force $distPath | Out-Null
Remove-Item -Recurse -Force (Join-Path $distPath 'Blablabla.exe'), (Join-Path $distPath '_internal') -ErrorAction SilentlyContinue
Copy-Item -Recurse (Join-Path $buildPath 'onedir\Blablabla\*') $distPath
Write-Host "Ejecutable: $distPath\Blablabla.exe"
