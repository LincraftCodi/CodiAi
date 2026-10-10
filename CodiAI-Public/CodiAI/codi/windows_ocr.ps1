$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$taskAwaitMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetGenericArguments().Count -eq 1 } | Select-Object -First 1
function Await-OcrOperation($operation, $resultType) {
    $taskOperation = $taskAwaitMethod.MakeGenericMethod($resultType).Invoke($null, @($operation))
    if (-not $taskOperation.Wait(3500)) { throw 'OCR operation timeout' }
    return $taskOperation.Result
}
$taskStream = $null
$taskBitmap = $null
try {
    $taskEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $taskEngine) { throw 'No Windows OCR language installed' }
    $taskFile = Await-OcrOperation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:CODIAI_OCR_IMAGE)) ([Windows.Storage.StorageFile])
    $taskStream = Await-OcrOperation ($taskFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $taskDecoder = Await-OcrOperation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($taskStream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $taskBitmap = Await-OcrOperation ($taskDecoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $taskResult = Await-OcrOperation ($taskEngine.RecognizeAsync($taskBitmap)) ([Windows.Media.Ocr.OcrResult])
    $taskLatin = [regex]::Matches($taskResult.Text, '[A-Za-z]').Count
    $taskCyrillic = [regex]::Matches($taskResult.Text, '[\u0400-\u04ff]').Count
    if ($taskEngine.RecognizerLanguage.LanguageTag -notlike 'en*' -and $taskLatin -gt [Math]::Max(12, $taskCyrillic * 4)) {
        $taskEnglish = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object { $_.LanguageTag -like 'en*' } | Select-Object -First 1
        if ($null -ne $taskEnglish) {
            $taskEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($taskEnglish)
            $taskResult = Await-OcrOperation ($taskEngine.RecognizeAsync($taskBitmap)) ([Windows.Media.Ocr.OcrResult])
        }
    }
    $taskLines = @($taskResult.Lines | ForEach-Object { $_.Text })
    @{text=($taskLines -join "`n");language=$taskEngine.RecognizerLanguage.LanguageTag;method='windows_ocr'} | ConvertTo-Json -Compress
} finally {
    if ($null -ne $taskBitmap) { $taskBitmap.Dispose() }
    if ($null -ne $taskStream) { $taskStream.Dispose() }
}
