param([string]$OutputDirectory = 'docs/evidence/v0.2.0/domain-smoke')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
    if (Test-Path -LiteralPath $taskOutput) { throw 'Domain evidence output already exists' }
    if (-not $taskOutput.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence must stay inside workspace' }
    [void](New-Item -ItemType Directory -Path $taskOutput)
    $taskResults = @()
    foreach ($taskDomain in @('procurement','support','hr')) {
        $taskLines = @(& uv run --frozen ax demo --domain $taskDomain)
        if ($LASTEXITCODE -ne 0) { throw 'Domain demo failed' }
        $taskResult = ($taskLines -join "`n") | ConvertFrom-Json
        if (-not $taskResult.passed -or -not $taskResult.audit_intact -or -not $taskResult.duplicate_execution_same_result) { throw 'Domain evidence failed' }
        $taskResults += $taskResult
        Write-Output ('DOMAIN_SMOKE_PASSED domain=' + $taskDomain + ' audit=' + $taskResult.audit_intact + ' idempotent=' + $taskResult.duplicate_execution_same_result)
    }
    $taskReport = Join-Path $taskOutput 'synthetic-demos.json'
    [IO.File]::WriteAllText($taskReport, ($taskResults | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    Write-Output ('DOMAIN_EVIDENCE_COLLECTED domains=' + $taskResults.Count + ' sha256=' + (Get-FileHash -LiteralPath $taskReport -Algorithm SHA256).Hash.ToLowerInvariant())
} finally { Pop-Location }
