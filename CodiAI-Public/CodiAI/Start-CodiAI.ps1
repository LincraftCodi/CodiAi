$ErrorActionPreference = 'Stop'
$taskAppRoot = $PSScriptRoot
$taskPython = Join-Path $taskAppRoot 'runtime/python/python.exe'
$taskOllama = Join-Path $taskAppRoot 'runtime/ollama/ollama.exe'
if (-not (Test-Path -LiteralPath $taskOllama)) {
    $taskOllamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($taskOllamaCommand) { $taskOllama = $taskOllamaCommand.Source }
}
$taskLogs = Join-Path $taskAppRoot 'data/logs'
New-Item -ItemType Directory -Force -Path $taskLogs,(Join-Path $taskAppRoot 'runtime/temp') | Out-Null
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $taskAppRoot 'runtime/models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:GGML_VK_VISIBLE_DEVICES = '-1'
$env:OLLAMA_VULKAN = '0'
$env:OLLAMA_LLM_LIBRARY = 'cpu_avx2'
$env:TEMP = Join-Path $taskAppRoot 'runtime/temp'
$env:TMP = $env:TEMP
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Python runtime missing. See README.md.' }
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 }
catch {
    if (Test-Path -LiteralPath $taskOllama) {
        $taskEngine = Start-Process -FilePath $taskOllama -ArgumentList 'serve' -WorkingDirectory $taskAppRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskLogs 'ollama-out.log') -RedirectStandardError (Join-Path $taskLogs 'ollama-error.log') -PassThru
        $taskEngine.PriorityClass = 'BelowNormal'
    }
}
$taskRunning = $false
try {
    $taskHealth = Invoke-RestMethod 'http://127.0.0.1:8765/api/bootstrap' -TimeoutSec 2
    $taskRunning = $taskHealth.settings.name -ne $null
} catch {}
if (-not $taskRunning) {
    Start-Process -FilePath $taskPython -ArgumentList 'server.py' -WorkingDirectory $taskAppRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskLogs 'server-out.log') -RedirectStandardError (Join-Path $taskLogs 'server-error.log') | Out-Null
    for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
        Start-Sleep -Milliseconds 200
        try { $null = Invoke-RestMethod 'http://127.0.0.1:8765/api/bootstrap' -TimeoutSec 1; $taskRunning=$true; break } catch {}
    }
}
if (-not $taskRunning) { throw 'CodiAI server did not start. Check data/logs/server-error.log.' }
$taskBrowser = Join-Path ${env:ProgramFiles(x86)} 'Microsoft/Edge/Application/msedge.exe'
if (-not (Test-Path -LiteralPath $taskBrowser)) {
    $taskBrowser = Join-Path $env:ProgramFiles 'Google/Chrome/Application/chrome.exe'
}
if (-not (Test-Path -LiteralPath $taskBrowser)) { throw 'Edge or Chrome is required for the CodiAI app window.' }
$taskBrowserProfile = Join-Path $taskAppRoot 'data/window-profile'
$taskWindowArgs = @('--app=http://127.0.0.1:8765/?v=0.8.7', ('--user-data-dir="' + $taskBrowserProfile + '"'), '--disable-gpu', '--no-first-run', '--no-default-browser-check')
$taskOpenWindow = Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('msedge.exe','chrome.exe') -and $_.CommandLine -like ('*' + $taskBrowserProfile + '*') -and $_.CommandLine -notlike '*--type=*' }
if (-not $taskOpenWindow) { Start-Process -FilePath $taskBrowser -ArgumentList $taskWindowArgs -WorkingDirectory $taskAppRoot | Out-Null }
Start-Process -FilePath (Join-Path $taskAppRoot 'runtime/python/pythonw.exe') -ArgumentList 'widget.py' -WorkingDirectory $taskAppRoot -WindowStyle Hidden | Out-Null
