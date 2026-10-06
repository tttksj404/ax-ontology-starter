param(
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [string]$ContractPath = 'templates/advisors/implementation-review.md'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
    if (Test-Path -LiteralPath $taskOutput) { throw 'OutputDirectory must be a new directory' }
    $taskContract = (Resolve-Path -LiteralPath $ContractPath).Path
    $taskFiles = @('README.md','pyproject.toml','docs/SECURITY_MODEL.md','docs/ARCHITECTURE.md')
    $taskFiles += @(Get-ChildItem -LiteralPath src,tests -Filter '*.py' -File -Recurse | Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' } | ForEach-Object { $_.FullName.Substring($taskRoot.Length + 1) } | Sort-Object)
    $taskBuilder = [Text.StringBuilder]::new()
    [void]$taskBuilder.AppendLine([IO.File]::ReadAllText($taskContract))
    $taskManifest = @()
    foreach ($taskFile in $taskFiles) {
        $taskFull = (Resolve-Path -LiteralPath $taskFile).Path
        $taskHash = (Get-FileHash -LiteralPath $taskFull -Algorithm SHA256).Hash.ToLowerInvariant()
        $taskManifest += [pscustomobject]@{path=$taskFile.Replace('\','/');sha256=$taskHash;bytes=(Get-Item -LiteralPath $taskFull).Length}
        [void]$taskBuilder.AppendLine("`n--- FILE: $taskFile SHA256: $taskHash ---")
        $taskLine = 0
        foreach ($taskText in [IO.File]::ReadAllLines($taskFull)) {
            $taskLine++
            [void]$taskBuilder.AppendLine(('{0,4} | {1}' -f $taskLine,$taskText))
        }
    }
    [void](New-Item -ItemType Directory -Path $taskOutput)
    [IO.File]::WriteAllText((Join-Path $taskOutput 'prompt.md'),$taskBuilder.ToString(),[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $taskOutput 'source-manifest.json'),($taskManifest | ConvertTo-Json -Depth 3),[Text.UTF8Encoding]::new($false))
    Write-Output ('REVIEW_PACKET_CREATED files=' + $taskManifest.Count + ' bytes=' + (Get-Item -LiteralPath (Join-Path $taskOutput 'prompt.md')).Length)
    Write-Output 'Review packet for accidental secrets and permitted external disclosure before calling an advisor.'
} finally { Pop-Location }
