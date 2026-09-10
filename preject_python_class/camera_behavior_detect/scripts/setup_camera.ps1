$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uvExecutable = if ($uvCommand) { $uvCommand.Source } else { $null }
if (-not $uvCommand) {
    $userUv = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (Test-Path -LiteralPath $userUv) { $uvExecutable = $userUv }
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if ($uvExecutable) {
        & $uvExecutable venv --python 3.12 .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv .venv
    } else {
        python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or uv, then run setup_camera.bat again.' }
}
if ($uvExecutable) {
    & $uvExecutable pip install --python $pythonPath -r requirements.txt
} else {
    & $pythonPath -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Could not set up pip.' }
    & $pythonPath -m pip install -r requirements.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network and retry.' }
& $pythonPath -X utf8 scripts\download_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Check the network and retry.' }
Write-Host 'Ready. Double-click start_camera.bat to test, or start_fake.bat for keyboard simulation.'
