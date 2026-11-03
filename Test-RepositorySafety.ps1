$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$files = & git -C $root ls-files --cached --others --exclude-standard
if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate task repository files.' }
$forbidden = @($files | Where-Object { $_ -match '(^|/)(state|vault|data|Pass|Private|\.env)(/|$)' -or $_ -match '(accounts\.json|sessions\.sqlite|\.ppk$|\.pem$|\.key$|credentials\.local)' })
if ($forbidden.Count) { throw 'A private runtime or credential file would be published.' }
foreach ($relative in $files) {
    $path = Join-Path $root $relative
    if ([IO.Path]::GetExtension($path) -notin @('.py','.js','.md','.json','.yml','.yaml','.ps1','.txt','.conf')) { continue }
    $text = [IO.File]::ReadAllText($path)
    if ($text -match '-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----' -or $text -match 'gh[pousr]_[A-Za-z0-9]{30,}') {
        throw 'Potential credential detected; publication stopped.'
    }
}
Write-Output ('Repository safety PASS; files='+$files.Count)
