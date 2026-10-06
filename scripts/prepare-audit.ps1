param(
    [string]$HeaderPath = 'docs/evidence/v0.2.0/final-audit-header.md',
    [string]$OutputPath = 'docs/evidence/v0.2.0/final-audit-request.md',
    [string]$ManifestPath = 'docs/evidence/v0.2.0/final-audit-input-manifest.json',
    [string[]]$AdditionalPaths = @(),
    [string[]]$TestPaths = @(),
    [ValidateSet('full','namespace')][string]$Scope = 'full'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskOutput = [IO.Path]::GetFullPath($OutputPath)
    $taskManifestOutput = [IO.Path]::GetFullPath($ManifestPath)
    foreach ($taskTarget in @($taskOutput, $taskManifestOutput)) {
        if (-not $taskTarget.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Audit output must stay inside workspace' }
        if (Test-Path -LiteralPath $taskTarget) { throw 'Frozen audit output already exists' }
    }
    $taskPaths = @(rg --files src --glob '*.py')
    if ($LASTEXITCODE -ne 0) { throw 'Source enumeration failed' }
    if ($TestPaths.Count -eq 0) {
        $taskPaths += @(rg --files tests --glob '*.py')
        if ($LASTEXITCODE -ne 0) { throw 'Test enumeration failed' }
    } else {
        foreach ($taskTestPath in $TestPaths) {
            if ($taskTestPath -notmatch '^tests/[A-Za-z0-9_/]+\.py$' -or -not (Test-Path -LiteralPath $taskTestPath -PathType Leaf)) {
                throw 'Invalid audit test selection'
            }
        }
        $taskPaths += $TestPaths
    }
    if ($Scope -eq 'namespace') {
        $taskPaths += @(
            'pyproject.toml', 'README.md',
            'docs/ADOPTION.md', 'docs/ARCHITECTURE.md', 'docs/SECURITY_MODEL.md',
            'docs/OPERATIONS.md', 'docs/UPGRADE_GUIDE.md', 'docs/V02_GUIDE.md',
            'scripts/check.ps1', 'scripts/check-package.ps1', 'scripts/package.ps1',
            'scripts/verify-package.ps1', 'scripts/check-delivery.ps1',
            'scripts/run-opus.ps1', 'scripts/prepare-audit.ps1', 'scripts/publish-advisor-evidence.ps1',
            'templates/advisors/no-hooks.json', 'templates/advisors/no-mcp.json'
        )
    } else {
        $taskPaths += @(
        'pyproject.toml', 'uv.lock', 'README.md',
        'docs/ADOPTION.md', 'docs/ARCHITECTURE.md', 'docs/SECURITY_MODEL.md',
        'docs/OPERATIONS.md', 'docs/UPGRADE_GUIDE.md', 'docs/V02_GUIDE.md', 'docs/LEARNING_GUIDE.md',
        'scripts/check.ps1', 'scripts/check-package.ps1', 'scripts/package.ps1',
        'scripts/verify-package.ps1', 'scripts/check-delivery.ps1', 'scripts/run-opus.ps1', 'scripts/prepare-audit.ps1',
        'templates/advisors/no-hooks.json', 'templates/advisors/no-mcp.json',
        'examples/providers/offline.json', 'examples/providers/local.json',
        'examples/providers/private-gateway.json', 'examples/providers/cloud-gateway.json',
        'docs/evidence/v0.2.0/verification-index.json', 'docs/evidence/v0.2.0/final-checks.txt',
        'docs/evidence/v0.2.0/final-static-checks.txt', 'docs/evidence/v0.2.0/final-wheel-smoke.txt',
        'docs/evidence/v0.2.0/final-no-excuse.txt'
        )
    }
    $taskPaths += $AdditionalPaths
    $taskPaths = @($taskPaths | Sort-Object -Unique)
    $taskManifest = @($taskPaths | ForEach-Object {
        [pscustomobject]@{
            path=$_.Replace('\','/')
            sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
            bytes=(Get-Item -LiteralPath $_).Length
        }
    })
    [IO.File]::WriteAllText($taskManifestOutput, ($taskManifest | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    $taskWriter = [IO.StreamWriter]::new($taskOutput, $false, [Text.UTF8Encoding]::new($false))
    try {
        $taskWriter.WriteLine([IO.File]::ReadAllText((Resolve-Path -LiteralPath $HeaderPath).Path))
        $taskWriter.WriteLine('')
        $taskWriter.WriteLine('Frozen input manifest SHA-256: ' + (Get-FileHash -LiteralPath $taskManifestOutput -Algorithm SHA256).Hash.ToLowerInvariant())
        foreach ($taskFile in $taskManifest) {
            $taskCurrentHash = (Get-FileHash -LiteralPath $taskFile.path -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($taskCurrentHash -cne $taskFile.sha256) { throw 'Source changed during freeze' }
            $taskWriter.WriteLine('')
            $taskWriter.WriteLine('===== FILE ' + $taskFile.path + ' SHA256=' + $taskFile.sha256 + ' BYTES=' + $taskFile.bytes + ' =====')
            $taskLine = 0
            foreach ($taskText in [IO.File]::ReadAllLines((Join-Path $taskRoot $taskFile.path))) {
                $taskLine++
                $taskWriter.WriteLine(('{0:D4}| ' -f $taskLine) + $taskText)
            }
            $taskWriter.WriteLine('===== END FILE =====')
        }
    } finally { $taskWriter.Dispose() }
    Write-Output ('AUDIT_INPUT_FROZEN files=' + $taskManifest.Count + ' bytes=' + (Get-Item -LiteralPath $taskOutput).Length + ' sha256=' + (Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash.ToLowerInvariant())
} finally { Pop-Location }
