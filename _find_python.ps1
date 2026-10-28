# _find_python.ps1
# Lokalizuje Python 3 z Tkinterem.
# Uzycie: powershell -NoProfile -ExecutionPolicy Bypass -File _find_python.ps1 [gui|console]
#   gui     -> zwraca pythonw.exe (bez okna konsoli)
#   console -> zwraca python.exe
# Wynik: jedna linia ze sciezka do interpretera; kod wyjscia 1 = nie znaleziono.

param([string]$Mode = "console")

$cands = New-Object System.Collections.ArrayList

function Add-Cand {
    param([string]$p)
    if (-not $p) { return }
    $p = $p.Trim('"')
    if (-not $cands.Contains($p)) { [void]$cands.Add($p) }
}

function Test-Py {
    param([string]$exe)
    if (-not $exe) { return $false }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { return $false }
    if ($exe -like "*\WindowsApps\*") { return $false }   # atrapa ze Sklepu MS
    try {
        $out = & $exe -c "import sys,tkinter;print(sys.version_info[0])" 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
        return ((($out | Out-String).Trim()) -eq "3")
    } catch {
        return $false
    }
}

# 1) jawne wskazanie uzytkownika
Add-Cand $env:ODX_GUI_PYTHON

# 2) interpretery widoczne w PATH
foreach ($n in @("pythonw.exe", "python.exe")) {
    $c = Get-Command $n -ErrorAction SilentlyContinue
    if ($c) { Add-Cand $c.Source }
}

# 3) launcher "py"
$py = Get-Command py.exe -ErrorAction SilentlyContinue
if ($py) {
    try {
        $real = (& $py.Source -3 -c "import sys;print(sys.executable)" 2>$null | Out-String).Trim()
        if ($real) { Add-Cand $real; Add-Cand ($real -replace 'python\.exe$', 'pythonw.exe') }
    } catch { }
}

# 4) rejestr - instalator python.org zapisuje ExecutablePath
$hives = @(
    "HKCU:\Software\Python\PythonCore",
    "HKLM:\Software\Python\PythonCore",
    "HKLM:\Software\WOW6432Node\Python\PythonCore"
)
foreach ($h in $hives) {
    if (-not (Test-Path $h)) { continue }
    $vers = Get-ChildItem $h -ErrorAction SilentlyContinue | Sort-Object PSChildName -Descending
    foreach ($v in $vers) {
        $ip = Join-Path $v.PSPath "InstallPath"
        if (-not (Test-Path $ip)) { continue }
        foreach ($name in @("WindowedExecutablePath", "ExecutablePath")) {
            $val = (Get-ItemProperty -Path $ip -Name $name -ErrorAction SilentlyContinue).$name
            if ($val) { Add-Cand $val }
        }
        $root = (Get-ItemProperty -Path $ip -ErrorAction SilentlyContinue)."(default)"
        if ($root) {
            Add-Cand (Join-Path $root "pythonw.exe")
            Add-Cand (Join-Path $root "python.exe")
        }
    }
}

# 5) typowe katalogi instalacji
$roots = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python"),
    $env:ProgramFiles,
    ${env:ProgramFiles(x86)},
    "C:\"
)
foreach ($r in $roots) {
    if (-not $r) { continue }
    if (-not (Test-Path $r)) { continue }
    Get-ChildItem -Path $r -Filter "Python3*" -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object {
            Add-Cand (Join-Path $_.FullName "pythonw.exe")
            Add-Cand (Join-Path $_.FullName "python.exe")
        }
}

# 6) ostatnia szansa: przenosne Pythony obok ODX (np. katalog Portable)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$parent1 = Split-Path -Parent $here                       # katalog ODX
$parent2 = Split-Path -Parent $parent1                    # np. Portable
foreach ($dir in @($parent2, $parent1)) {
    if (-not $dir) { continue }
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -Path $dir -Directory -ErrorAction SilentlyContinue |
        ForEach-Object {
            Add-Cand (Join-Path $_.FullName "pythonw.exe")
            Add-Cand (Join-Path $_.FullName "python.exe")
        }
}

$chosen = $null
foreach ($c in $cands) {
    if (Test-Py $c) { $chosen = $c; break }
}

if (-not $chosen) { exit 1 }

# dopasuj typ interpretera do trybu pracy
$dir = Split-Path -Parent $chosen
$leaf = Split-Path -Leaf $chosen
if ($Mode -eq "gui") {
    if ($leaf -ne "pythonw.exe") {
        $w = Join-Path $dir "pythonw.exe"
        if (Test-Path -LiteralPath $w) { $chosen = $w }
    }
} else {
    if ($leaf -ne "python.exe") {
        $p = Join-Path $dir "python.exe"
        if (Test-Path -LiteralPath $p) { $chosen = $p }
    }
}

Write-Output $chosen
exit 0
