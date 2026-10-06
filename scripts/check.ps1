$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    & uv run --frozen ruff check src tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & uv run --frozen ruff format --check src tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & uv run --frozen basedpyright
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & uv run --frozen pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Output 'AX_CHECKS_PASSED'
} finally { Pop-Location }
