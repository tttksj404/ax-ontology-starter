param([string]$OutputFile = 'artifacts/ax-ontology-starter-v0.3.0.zip')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskOutput = [IO.Path]::GetFullPath($OutputFile)
    if (Test-Path -LiteralPath $taskOutput) { throw 'Archive output already exists' }
    $taskPaths = @('README.md','pyproject.toml','uv.lock','.python-version','.gitignore')
    foreach ($taskDirectory in @('src','tests','docs','examples','templates','scripts')) {
        $taskPaths += @(Get-ChildItem -LiteralPath $taskDirectory -File -Recurse | Where-Object {
            $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Extension -in @('.py','.md','.json','.txt','.ps1') -and $_.FullName -notmatch '[\\/]evidence[\\/]v[0-9]+\.[0-9]+\.[0-9]+[\\/].*-output\.json$'
        } | ForEach-Object { $_.FullName.Substring($taskRoot.Length + 1) })
    }
    $taskPaths = @($taskPaths | Sort-Object -Unique)
    $taskManifest = @($taskPaths | ForEach-Object {
        [pscustomobject]@{path=$_.Replace('\','/');sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant();bytes=(Get-Item -LiteralPath $_).Length}
    })
    [void](New-Item -ItemType Directory -Path (Split-Path -Parent $taskOutput) -Force)
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $taskZip = [IO.Compression.ZipFile]::Open($taskOutput,[IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($taskFile in $taskManifest) {
            $taskEntry = $taskZip.CreateEntry('ax-ontology-starter/' + $taskFile.path)
            $taskInput = [IO.File]::OpenRead((Join-Path $taskRoot $taskFile.path))
            $taskStream = $taskEntry.Open()
            try { $taskInput.CopyTo($taskStream) } finally { $taskStream.Dispose(); $taskInput.Dispose() }
        }
        $taskManifestEntry = $taskZip.CreateEntry('ax-ontology-starter/DELIVERY_MANIFEST.json')
        $taskWriter = [IO.StreamWriter]::new($taskManifestEntry.Open(),[Text.UTF8Encoding]::new($false))
        try { $taskWriter.Write(($taskManifest | ConvertTo-Json -Depth 4)) } finally { $taskWriter.Dispose() }
    } finally { $taskZip.Dispose() }
    Write-Output ('AX_PACKAGE_CREATED files=' + $taskManifest.Count + ' bytes=' + (Get-Item -LiteralPath $taskOutput).Length + ' sha256=' + (Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash)
} finally { Pop-Location }
