$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Windows.Forms
$taskDialog = New-Object System.Windows.Forms.FolderBrowserDialog
$taskDialog.Description = 'Select the folder CodiAI should work in'
$taskDialog.ShowNewFolderButton = $true
if ($taskDialog.PSObject.Properties['AutoUpgradeEnabled']) { $taskDialog.AutoUpgradeEnabled = $true }
if ($env:CODIAI_SELECTED_FOLDER -and (Test-Path -LiteralPath $env:CODIAI_SELECTED_FOLDER -PathType Container)) {
    $taskDialog.SelectedPath = $env:CODIAI_SELECTED_FOLDER
} elseif (Test-Path -LiteralPath 'D:\') { $taskDialog.SelectedPath = 'D:\' }
$taskOwner = New-Object System.Windows.Forms.Form
$taskOwner.TopMost = $true
$taskOwner.ShowInTaskbar = $false
$taskOwner.Opacity = 0
$taskOwner.Show()
try {
    $taskResult = $taskDialog.ShowDialog($taskOwner)
    @{ cancelled = ($taskResult -ne [System.Windows.Forms.DialogResult]::OK); path = $(if ($taskResult -eq [System.Windows.Forms.DialogResult]::OK) { $taskDialog.SelectedPath } else { '' }) } | ConvertTo-Json -Compress
} finally { $taskOwner.Dispose(); $taskDialog.Dispose() }
