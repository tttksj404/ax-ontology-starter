$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    & uv build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $taskWheel = 'dist/ax_ontology_starter-0.3.0-py3-none-any.whl'
    & uv run --isolated --no-project --offline --with $taskWheel python -c "import inspect; from ax_starter.runtime import load_app; assert 'AX_DATA_CONTRACTS_FILE' in inspect.getsource(load_app); from ax_starter.knowledge import KnowledgeService; assert callable(KnowledgeService.import_snapshot); print('WHEEL_RUNTIME_CONFIG_VERIFIED')"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & uv run --isolated --no-project --offline --with $taskWheel python -m ax_starter demo --domain support
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & uv run --isolated --no-project --offline --with $taskWheel python -m tests.v03_runtime_smoke
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & uv run --isolated --no-project --offline --with $taskWheel python -m tests.v02_hardening_smoke
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    foreach ($taskDomain in @('procurement','support','hr')) {
        & uv run --isolated --no-project --offline --with $taskWheel python -m ax_starter wiki demo --domain $taskDomain
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Write-Output 'AX_PACKAGE_CHECK_PASSED'
} finally { Pop-Location }
