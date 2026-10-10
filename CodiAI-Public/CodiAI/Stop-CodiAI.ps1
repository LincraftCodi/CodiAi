$ErrorActionPreference = 'Stop'
$taskAppRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$taskRuntimeRoot = Join-Path $taskAppRoot 'runtime'
# Only CodiAI-owned processes. Other Ollama/Python programs are untouched.
$taskOwned = Get-CimInstance Win32_Process | Where-Object {
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($taskRuntimeRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) -or
    ($_.Name -in @('msedge.exe', 'chrome.exe') -and $_.CommandLine -and $_.CommandLine.Contains('--user-data-dir="' + (Join-Path $taskAppRoot 'data/window-profile') + '"')) -or
     ($_.Name -eq 'msedgewebview2.exe' -and $_.CommandLine -and $_.CommandLine.Contains((Join-Path $taskAppRoot 'data/browser-profile')))
}
foreach ($taskProcess in $taskOwned) {
    Stop-Process -Id $taskProcess.ProcessId -ErrorAction SilentlyContinue
}
Write-Output 'CodiAI stopped. Models and data are preserved.'
