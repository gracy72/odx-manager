# create_shortcut.ps1
# Tworzy skrot "ODX Manager" na pulpicie (uruchamia GUI bez okna konsoli).
# Uzycie:  powershell -NoProfile -ExecutionPolicy Bypass -File create_shortcut.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$gui = Join-Path $root "gui\odx_gui.py"
$icon = Join-Path $root "odx-gui.ico"

# 1) znajdz Pythona 3 z Tkinterem
$pyw = & (Join-Path $root "_find_python.ps1") gui
if (-not $pyw) {
    Write-Host "[BLAD] Nie znaleziono Pythona 3 z Tkinterem." -ForegroundColor Red
    Write-Host "       Zainstaluj Python 3 z python.org (opcja 'tcl/tk and IDLE')."
    Read-Host "Enter"
    exit 1
}

# 2) utworz skrot
$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop "ODX Manager.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = $pyw
# -E -s: pomija user-site (pip_system_certs.pth dokladal ~0,7 s do startu)
$sc.Arguments = '-E -s "' + $gui + '"'
$sc.WorkingDirectory = $root
$sc.Description = "ODX - Auto-Manager z Wykrywaniem GCP"
if ((Test-Path $icon) -and ((Get-Item $icon).Length -gt 1024)) {
    $sc.IconLocation = "$icon,0"
}
$sc.Save()

Write-Host "[OK] Skrot utworzony: $lnk"
Write-Host "     Interpreter: $pyw"
Read-Host "Enter"
