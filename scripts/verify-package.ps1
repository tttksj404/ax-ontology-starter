param([string]$ArchiveFile = 'artifacts/ax-ontology-starter-v0.3.0.zip')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskArchive = (Resolve-Path -LiteralPath $ArchiveFile).Path
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $taskZip = [IO.Compression.ZipFile]::OpenRead($taskArchive)
    try {
        $taskEntries = [Collections.Generic.Dictionary[string,IO.Compression.ZipArchiveEntry]]::new([StringComparer]::Ordinal)
        foreach ($taskEntry in $taskZip.Entries) {
            if ($taskEntry.FullName -notmatch '^ax-ontology-starter/' -or $taskEntry.FullName -match '(^|/)(\.omx|\.runtime|\.venv|__pycache__)(/|$)|(^|/)(demo-credentials|identities)\.json$|(^|/)\.\.(/|$)|\\|/evidence/v[0-9]+\.[0-9]+\.[0-9]+/.*-output\.json$') { throw 'Unexpected private or unsafe archive entry' }
            $taskEntries.Add($taskEntry.FullName,$taskEntry)
        }
        $taskManifestEntry = $taskEntries['ax-ontology-starter/DELIVERY_MANIFEST.json']
        $taskReader = [IO.StreamReader]::new($taskManifestEntry.Open(),[Text.UTF8Encoding]::new($false))
        try { $taskManifest = $taskReader.ReadToEnd() | ConvertFrom-Json } finally { $taskReader.Dispose() }
        if ($taskEntries.Count -ne $taskManifest.Count + 1) { throw 'Unlisted or missing archive entry' }
        $taskSeen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach ($taskFile in $taskManifest) {
            if (-not $taskSeen.Add($taskFile.path)) { throw 'Duplicate manifest path' }
            $taskEntry = $taskEntries['ax-ontology-starter/' + $taskFile.path]
            if ($null -eq $taskEntry -or $taskEntry.Length -ne $taskFile.bytes) { throw 'Archive size mismatch' }
            $taskHasher = [Security.Cryptography.SHA256]::Create()
            $taskStream = $taskEntry.Open()
            try { $taskHash = [BitConverter]::ToString($taskHasher.ComputeHash($taskStream)).Replace('-','').ToLowerInvariant() } finally { $taskStream.Dispose(); $taskHasher.Dispose() }
            if ($taskHash -cne $taskFile.sha256) { throw 'Archive hash mismatch' }
        }
        Write-Output ('AX_ARCHIVE_VERIFIED files=' + $taskManifest.Count + ' entries=' + $taskEntries.Count + ' private_entries=0 sha256=' + (Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256).Hash.ToLowerInvariant())
    } finally { $taskZip.Dispose() }
} finally { Pop-Location }
