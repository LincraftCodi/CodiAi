$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot 'runtime/python/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskPy = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $taskPy) { throw 'Install Python 3.12+ from python.org, including Tcl/Tk and the py launcher.' }
    & $taskPy.Source -3 -m venv (Join-Path $PSScriptRoot 'runtime/python')
    if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed.' }
}
& $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'data/logs') | Out-Null
Write-Output 'Setup complete. Install Ollama, then run Start-CodiAI.cmd and download a model in Models.'
