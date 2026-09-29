# kauz-tools-csgo installer/updater. Usage: install.bat [path\to\game\csgo\cfg]
$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot 'cfg'
$rel = 'steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg'

function Find-Cfg {
    $steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue).SteamPath
    if (-not $steam) { return $null }
    $libs = @($steam)
    $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
    if (Test-Path $vdf) {
        $libs += [regex]::Matches((Get-Content $vdf -Raw), '"path"\s+"([^"]+)"') | ForEach-Object { $_.Groups[1].Value -replace '\\\\', '\' }
    }
    foreach ($lib in $libs) {
        $cfg = Join-Path $lib $rel
        if (Test-Path $cfg) { return $cfg }
    }
}

# append $line to $file unless present; new files start with $header
function Add-Line($file, $line, $header) {
    $text = if (Test-Path $file) { Get-Content $file -Raw } elseif ($header) { "$header`n" } else { '' }
    if ($text -and ($text -split "`r?`n") -contains $line) { return }
    if ($text -and -not $text.EndsWith("`n")) { $text += "`n" }
    Set-Content $file ($text + "$line`n") -NoNewline -Encoding ascii
}

$cfg = if ($args[0]) { $args[0] } else { Find-Cfg }
while (-not $cfg -or -not (Test-Path $cfg)) {
    $cfg = Read-Host 'CS2 cfg folder not found. Paste the path to ...\game\csgo\cfg'
}

$kt = Join-Path $cfg 'kt'
if (Test-Path $kt) { Remove-Item $kt -Recurse -Force }
Copy-Item (Join-Path $src 'kt') $kt -Recurse
foreach ($hook in Get-ChildItem $src -Filter 'gamemode_*_server.cfg') {
    $lines = Get-Content $hook.FullName
    Add-Line (Join-Path $cfg $hook.Name) $lines[1] $lines[0]
}
Add-Line (Join-Path $cfg 'autoexec.cfg') 'exec kt/init'

Write-Host "kauz-tools installed to $cfg"
Write-Host 'If not done yet: Steam > CS2 > Properties > General > Launch Options: +exec autoexec'
