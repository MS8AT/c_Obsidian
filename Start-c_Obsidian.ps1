param(
    [string]$VaultPath = '',
    [ValidateSet('ru','en','zh')][string]$Language = 'ru',
    [ValidateRange(1024,65535)][int]$Port = 8765,
    [switch]$ReadOnly
)
$ErrorActionPreference = 'Stop'
$moduleRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$driveName = [IO.Path]::GetPathRoot($moduleRoot).TrimEnd('\',':')
$drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
if ($moduleRoot.StartsWith('\\') -or ($null -ne $drive -and $drive.DisplayRoot -like '\\*')) {
    throw 'Use a SHA-256 verified local module copy. See docs/INTEGRATION_RU.md.'
}
if (-not $VaultPath) { $VaultPath = Join-Path $moduleRoot 'demo-vault' }
$entry = Join-Path $moduleRoot 'obsidian.py'
$arguments = @('-3','-B',$entry,'--vault',$VaultPath,'--lang',$Language,'serve','--open','--port',[string]$Port)
if (-not $ReadOnly) { $arguments += '--write' }
& py @arguments
if ($LASTEXITCODE -ne 0) { throw "c_Obsidian exited with code $LASTEXITCODE" }
