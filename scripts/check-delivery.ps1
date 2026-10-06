$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskFiles = @('README.md') + @(Get-ChildItem -LiteralPath docs -File -Filter '*.md' | ForEach-Object { $_.FullName })
    $taskLinks = 0
    foreach ($taskFile in $taskFiles) {
        $taskFull = (Resolve-Path -LiteralPath $taskFile).Path
        foreach ($taskMatch in [regex]::Matches([IO.File]::ReadAllText($taskFull), '\[[^\]]+\]\(([^)]+)\)')) {
            $taskHref = $taskMatch.Groups[1].Value
            if ($taskHref -match '^(https?://|#)') { continue }
            $taskHref = $taskHref.Split('#')[0]
            $taskPath = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $taskFull) $taskHref))
            if (-not (Test-Path -LiteralPath $taskPath)) { throw ('missing local documentation target: ' + $taskHref) }
            $taskLinks++
        }
    }
    Write-Output ('AX_DELIVERY_LINKS_PASSED documents=' + $taskFiles.Count + ' local_links=' + $taskLinks)
} finally { Pop-Location }
