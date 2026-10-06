param(
    [Parameter(Mandatory = $true)][string]$PromptPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$taskPrompt = (Resolve-Path -LiteralPath $PromptPath).Path
$taskOutput = [IO.Path]::GetFullPath($OutputPath)
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskCli = (Get-Command claude.exe -ErrorAction Stop).Source
$taskArgs = @('-p', '--model', 'claude-opus-5-5', '--effort', 'max', '--output-format', 'json', '--tools', '', '--disable-slash-commands', '--no-session-persistence', '--no-chrome', '--setting-sources', '', '--settings', (Join-Path $taskRoot 'templates/advisors/no-hooks.json'), '--strict-mcp-config', '--mcp-config', (Join-Path $taskRoot 'templates/advisors/no-mcp.json'))
$taskStart = [Diagnostics.ProcessStartInfo]::new()
$taskStart.FileName = $taskCli
$taskStart.WorkingDirectory = $taskRoot
$taskStart.UseShellExecute = $false
$taskStart.CreateNoWindow = $true
$taskStart.RedirectStandardInput = $true
$taskStart.RedirectStandardOutput = $true
$taskStart.RedirectStandardError = $true
$taskStart.StandardOutputEncoding = [Text.UTF8Encoding]::new($false)
$taskQuote = {param([string]$arg) '"' + ($arg -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'}
$taskStart.Arguments = ($taskArgs | ForEach-Object { & $taskQuote $_ }) -join ' '
$taskProcess = [Diagnostics.Process]::new()
$taskProcess.StartInfo = $taskStart
try {
    [void]$taskProcess.Start()
    $taskStdout = $taskProcess.StandardOutput.ReadToEndAsync()
    $taskStderr = $taskProcess.StandardError.ReadToEndAsync()
    $taskWriter = [IO.StreamWriter]::new($taskProcess.StandardInput.BaseStream, [Text.UTF8Encoding]::new($false))
    $taskWriter.Write([IO.File]::ReadAllText($taskPrompt))
    $taskWriter.Dispose()
    $taskProcess.WaitForExit()
    [IO.File]::WriteAllText($taskOutput, $taskStdout.Result, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($taskOutput + '.stderr', $taskStderr.Result, [Text.UTF8Encoding]::new($false))
    if ($taskProcess.ExitCode -ne 0) { Write-Output ('OPUS_CALL_FAILED exit=' + $taskProcess.ExitCode); exit $taskProcess.ExitCode }
    $taskResult = Get-Content -LiteralPath $taskOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Output ('OPUS_RESULT model=' + ($taskResult.modelUsage.PSObject.Properties.Name -join ',') + ' effort=max error=' + $taskResult.is_error)
    Write-Output ('OPUS_OUTPUT sha256=' + (Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash + ' bytes=' + (Get-Item -LiteralPath $taskOutput).Length)
    if ($taskResult.is_error) { Write-Output 'OPUS_MODEL_ERROR'; exit 2 }
    Write-Output 'OPUS_CALL_COMPLETE'
} finally { $taskProcess.Dispose() }
