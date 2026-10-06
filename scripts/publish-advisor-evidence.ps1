param(
    [Parameter(Mandatory = $true)][string]$PromptPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$PublicPath,
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [Parameter(Mandatory = $true)][string]$ExpectedRawSha256,
    [string]$TaskPath = 'docs/evidence/v0.2.0/user-request.md'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
function Get-WorkspacePath([string]$Path) {
    $taskAbsolute = [IO.Path]::GetFullPath((Join-Path $taskRoot $Path))
    if (-not $taskAbsolute.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Advisor artifact must stay inside workspace'
    }
    return $taskAbsolute
}
$taskRaw = Get-WorkspacePath $OutputPath
$taskPrompt = Get-WorkspacePath $PromptPath
$taskManifest = Get-WorkspacePath $ManifestPath
$taskOriginal = Get-WorkspacePath $TaskPath
$taskPublic = Get-WorkspacePath $PublicPath
$taskArtifact = Get-WorkspacePath $ArtifactPath
foreach ($taskTarget in @($taskPublic, $taskArtifact)) {
    if (Test-Path -LiteralPath $taskTarget) { throw 'Advisor proof already exists' }
}
$taskRawHash = (Get-FileHash -LiteralPath $taskRaw -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskRawHash -cne $ExpectedRawSha256) { throw 'Advisor raw output hash mismatch' }
$taskResult = [IO.File]::ReadAllText($taskRaw) | ConvertFrom-Json
$taskModels = @($taskResult.modelUsage.PSObject.Properties.Name)
if ($taskModels.Count -ne 1 -or $taskModels[0] -cne 'claude-opus-5-5') { throw 'Unexpected advisor model' }
if ($taskResult.is_error -isnot [bool] -or $taskResult.is_error) { throw 'Advisor response failed' }
if ($taskResult.result -notmatch '\AVERDICT: (PASS|NEEDS_FIX)(?:\r?\n|$)') { throw 'Missing advisor verdict' }
$taskVerdict = $Matches[1]
$taskManifestHash = (Get-FileHash -LiteralPath $taskManifest -Algorithm SHA256).Hash.ToLowerInvariant()
$taskPromptText = [IO.File]::ReadAllText($taskPrompt)
if (-not $taskPromptText.Contains('Frozen input manifest SHA-256: ' + $taskManifestHash)) { throw 'Prompt manifest binding mismatch' }
$taskPublicResult = [ordered]@{
    schema='ax-advisor-public/v1'
    model=$taskModels[0]
    effort='max'
    effort_evidence='--effort max in scripts/run-opus.ps1; response confirms model only'
    is_error=$taskResult.is_error
    verdict=$taskVerdict
    scope='static supplied-source audit of local reference runtime; no code execution or company deployment validation'
    raw_sha256=$taskRawHash
    prompt_sha256=(Get-FileHash -LiteralPath $taskPrompt -Algorithm SHA256).Hash.ToLowerInvariant()
    input_manifest_sha256=$taskManifestHash
    invocation_script_sha256=(Get-FileHash -LiteralPath (Join-Path $taskRoot 'scripts/run-opus.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()
    capture_disposition='CLI error=False line is a response-status value; raw JSON is_error=false was inspected explicitly'
    result=$taskResult.result
}
$taskPrivateText = '# Independent advisor record' + "`n`n" +
    '## Original user task' + "`n`n" + [IO.File]::ReadAllText($taskOriginal) + "`n`n" +
    '## Invocation and scope' + "`n`n" +
    'claude-opus-5-5 --effort max; tools/hooks/MCP disabled; static supplied-source review only.' + "`n`n" +
    'Raw output SHA-256: ' + $taskRawHash + "`n" +
    'Input manifest SHA-256: ' + $taskManifestHash + "`n`n" +
    '## Exact prompt' + "`n`n" + $taskPromptText + "`n`n" +
    '## Original raw response' + "`n`n" + '```json' + "`n" + [IO.File]::ReadAllText($taskRaw) + "`n" + '```' + "`n`n" +
    '## Result and follow-up' + "`n`n" +
    'Verdict: ' + $taskVerdict + '. Read the exact response above for findings and scope. ' +
    'Nonblocking recommendations require implementation evidence and a new audit after any code changes. ' +
    'This record is private evidence and is excluded from the delivery ZIP.' + "`n"
[IO.File]::WriteAllText($taskPublic, ($taskPublicResult | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($taskArtifact, $taskPrivateText, [Text.UTF8Encoding]::new($false))
Write-Output ('ADVISOR_PROOF_PUBLISHED verdict=' + $taskVerdict + ' raw_sha256=' + $taskRawHash)
