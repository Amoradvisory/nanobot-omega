#!/usr/bin/env python
"""
pc_master.py — Module PC-Master: Controle Avance de l'Environnement Windows

Permet a l'agent d'interagir avec le systeme Windows comme un operateur expert.
Fenetrage, saisie, focus, detection d'etat, automatisation multi-apps.

Usage importable:
    from modules.pc_master import pc

    pc.list_windows()
    pc.focus_window("Notepad")
    pc.send_keys("^s")  # Ctrl+S
    pc.type_text("Bonjour")
    pc.click(100, 200)
    pc.screenshot("C:/temp/screen.png")
    pc.get_active_window()
    pc.wait_for_window("Chrome", timeout=10)
    pc.open_url_in_tab("https://example.com")

Usage CLI:
    python modules/pc_master.py windows              # Lister les fenetres
    python modules/pc_master.py focus "Chrome"        # Focus une fenetre
    python modules/pc_master.py type "Hello world"    # Taper du texte
    python modules/pc_master.py keys "^s"             # Envoyer des touches
    python modules/pc_master.py click 500 300         # Cliquer
    python modules/pc_master.py screenshot            # Capture d'ecran
    python modules/pc_master.py active                # Fenetre active
    python modules/pc_master.py url "https://..."     # Ouvrir URL dans onglet
    python modules/pc_master.py processes             # Processus actifs
    python modules/pc_master.py test                  # Tests
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CHROME_LAUNCHER = Path("C:/AI/nanobot-omega/modules/chrome_launcher.ps1")


def _ps(cmd: str, timeout: int = 15) -> str:
    """Execute PowerShell et retourne stdout."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout
    )
    return result.stdout.strip()


def _ps_json(cmd: str, timeout: int = 15) -> Any:
    """Execute PowerShell et parse le JSON de sortie."""
    raw = _ps("& {\n" + cmd + "\n} | ConvertTo-Json -Depth 5 -Compress", timeout)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class PCMaster:
    """Controle avance du poste Windows."""

    # --- Fenetres ---

    def list_windows(self) -> list[dict]:
        """Liste toutes les fenetres visibles avec titre, processus, position."""
        cmd = """
Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } |
Select-Object Id, ProcessName, MainWindowTitle,
    @{N='Left';E={
        Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class W{[DllImport("user32.dll")]public static extern bool GetWindowRect(IntPtr h,out RECT r);[StructLayout(LayoutKind.Sequential)]public struct RECT{public int L,T,R,B;}}' -PassThru | Out-Null
        $r = New-Object W+RECT
        [W]::GetWindowRect($_.MainWindowHandle,[ref]$r) | Out-Null
        $r.L
    }},
    @{N='Top';E={0}},
    @{N='Width';E={0}},
    @{N='Height';E={0}}
"""
        # Simplified version that works reliably
        cmd = """
Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -ne '' } |
Select-Object Id, ProcessName, MainWindowTitle |
Sort-Object ProcessName
"""
        data = _ps_json(cmd)
        if isinstance(data, dict):
            data = [data]
        return data if isinstance(data, list) else []

    def get_active_window(self) -> dict:
        """Retourne la fenetre active (au premier plan)."""
        cmd = """
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class ActiveWin {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
}
'@
$h = [ActiveWin]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 256
[ActiveWin]::GetWindowText($h, $sb, 256) | Out-Null
$pid = 0
[ActiveWin]::GetWindowThreadProcessId($h, [ref]$pid) | Out-Null
$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
[PSCustomObject]@{
    Title = $sb.ToString()
    ProcessName = if($proc){$proc.ProcessName}else{'unknown'}
    PID = $pid
    Handle = $h.ToInt64()
}
"""
        return _ps_json(cmd)

    def focus_window(self, title_pattern: str) -> bool:
        """Met au premier plan la fenetre dont le titre contient le pattern."""
        cmd = f"""
$proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{title_pattern}*' -and $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{
    Add-Type @'
using System;using System.Runtime.InteropServices;
public class FW {{ [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c); }}
'@
    [FW]::ShowWindow($proc.MainWindowHandle, 9) | Out-Null
    [FW]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    Write-Output "OK:$($proc.MainWindowTitle)"
}} else {{ Write-Output "NOT_FOUND" }}
"""
        result = _ps(cmd)
        return result.startswith("OK:")

    def wait_for_window(self, title_pattern: str, timeout: int = 10) -> bool:
        """Attend qu'une fenetre apparaisse (polling rapide)."""
        end = time.time() + timeout
        while time.time() < end:
            windows = self.list_windows()
            for w in windows:
                if isinstance(w, dict) and title_pattern.lower() in str(w.get("MainWindowTitle", "")).lower():
                    return True
            time.sleep(0.5)
        return False

    def close_window(self, title_pattern: str) -> bool:
        """Ferme la fenetre correspondant au pattern."""
        cmd = f"""
$proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{title_pattern}*' -and $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if ($proc) {{ $proc.CloseMainWindow() | Out-Null; Write-Output "OK" }} else {{ Write-Output "NOT_FOUND" }}
"""
        return _ps(cmd) == "OK"

    # --- Saisie ---

    def send_keys(self, keys: str) -> bool:
        """Envoie des touches clavier (syntaxe SendKeys)."""
        cmd = f"""
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait('{keys}')
Write-Output "OK"
"""
        return _ps(cmd) == "OK"

    def type_text(self, text: str) -> bool:
        """Tape du texte via le presse-papiers (gere accents/unicode)."""
        # Escape pour PowerShell
        escaped = text.replace("'", "''")
        cmd = f"""
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Clipboard]::SetText('{escaped}')
[System.Windows.Forms.SendKeys]::SendWait('^v')
Write-Output "OK"
"""
        return _ps(cmd) == "OK"

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> bool:
        """Cliquer a une position ecran."""
        btn_flag = "0x0002; 0x0004" if button == "left" else "0x0008; 0x0010"
        dbl = f"""
[M]::mouse_event(0x0002,0,0,0,0);[M]::mouse_event(0x0004,0,0,0,0)
Start-Sleep -Milliseconds 50
[M]::mouse_event(0x0002,0,0,0,0);[M]::mouse_event(0x0004,0,0,0,0)
""" if double else f"[M]::mouse_event({btn_flag.split(';')[0]},0,0,0,0);[M]::mouse_event({btn_flag.split(';')[1].strip()},0,0,0,0)"

        cmd = f"""
Add-Type @'
using System;using System.Runtime.InteropServices;
public class M {{
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint dx,uint dy,uint d,int e);
}}
'@
[M]::SetCursorPos({x},{y})
Start-Sleep -Milliseconds 50
{dbl}
Write-Output "OK"
"""
        return _ps(cmd) == "OK"

    # --- Screenshot ---

    def screenshot(self, path: str = "") -> str:
        """Capture d'ecran, retourne le chemin du fichier."""
        if not path:
            path = f"C:/AI/nanobot-omega/state/screenshot_{int(time.time())}.png"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        escaped = path.replace("\\", "\\\\").replace("'", "''")
        cmd = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($b.Width,$b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size)
$bmp.Save('{escaped}')
$g.Dispose();$bmp.Dispose()
Write-Output '{escaped}'
"""
        return _ps(cmd)

    # --- Chrome integration ---

    def open_url_in_tab(self, url: str) -> bool:
        """Ouvre une URL dans un onglet du Chrome agent (pas nouvelle fenetre)."""
        # Utiliser le chrome_launcher.ps1
        if CHROME_LAUNCHER.exists():
            result = _ps(f'& "{CHROME_LAUNCHER}" -Url "{url}"')
            return "OK" in result or "REUSE" in result
        # Fallback: CDP direct
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:9222/json/new?{url}", timeout=5)
            return True
        except Exception:
            # Dernier recours: start chrome
            subprocess.Popen(["cmd", "/c", "start", "chrome", url])
            return True

    def chrome_tabs(self) -> list[dict]:
        """Liste les onglets Chrome ouverts."""
        try:
            import urllib.request
            data = urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=3).read()
            tabs = json.loads(data)
            return [{"title": t.get("title", ""), "url": t.get("url", "")} for t in tabs if t.get("type") == "page"]
        except Exception:
            return []

    # --- Processus ---

    def list_processes(self, top: int = 20) -> list[dict]:
        """Top processus par utilisation CPU/memoire."""
        cmd = f"""
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First {top} |
Select-Object Id, ProcessName, @{{N='MemMB';E={{[math]::Round($_.WorkingSet64/1MB,1)}}}}, CPU
"""
        data = _ps_json(cmd)
        if isinstance(data, dict):
            data = [data]
        return data if isinstance(data, list) else []

    def kill_process(self, name_or_pid: str) -> bool:
        """Arreter un processus par nom ou PID."""
        try:
            pid = int(name_or_pid)
            cmd = f"Stop-Process -Id {pid} -Force; Write-Output OK"
        except ValueError:
            cmd = f"Stop-Process -Name '{name_or_pid}' -Force -ErrorAction SilentlyContinue; Write-Output OK"
        return _ps(cmd) == "OK"

    # --- Systeme ---

    def system_info(self) -> dict:
        """Info systeme rapide."""
        cmd = """
$cpu = (Get-CimInstance Win32_Processor).LoadPercentage
$os = (Get-CimInstance Win32_OperatingSystem)
$mem_total = [math]::Round($os.TotalVisibleMemorySize/1MB,1)
$mem_free = [math]::Round($os.FreePhysicalMemory/1MB,1)
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" | Select-Object @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,1)}}, @{N='TotalGB';E={[math]::Round($_.Size/1GB,1)}}
[PSCustomObject]@{
    CPU_Percent = $cpu
    RAM_Total_GB = $mem_total
    RAM_Free_GB = $mem_free
    Disk_Free_GB = $disk.FreeGB
    Disk_Total_GB = $disk.TotalGB
    Uptime_Hours = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours,1)
}
"""
        return _ps_json(cmd)


# --- Singleton ---
pc = PCMaster()


# --- CLI ---
def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    cmd = sys.argv[1].lower()

    if cmd == "windows":
        for w in pc.list_windows():
            if isinstance(w, dict):
                print(f"  [{w.get('Id','')}] {w.get('ProcessName','')} — {w.get('MainWindowTitle','')}")
    elif cmd == "active":
        print(json.dumps(pc.get_active_window(), ensure_ascii=False, indent=2, default=str))
    elif cmd == "focus" and len(sys.argv) >= 3:
        ok = pc.focus_window(sys.argv[2])
        print(f"Focus {'OK' if ok else 'ECHEC'}: {sys.argv[2]}")
    elif cmd == "type" and len(sys.argv) >= 3:
        text = " ".join(sys.argv[2:])
        ok = pc.type_text(text)
        print(f"Type {'OK' if ok else 'ECHEC'}")
    elif cmd == "keys" and len(sys.argv) >= 3:
        ok = pc.send_keys(sys.argv[2])
        print(f"Keys {'OK' if ok else 'ECHEC'}: {sys.argv[2]}")
    elif cmd == "click" and len(sys.argv) >= 4:
        ok = pc.click(int(sys.argv[2]), int(sys.argv[3]))
        print(f"Click {'OK' if ok else 'ECHEC'} @ ({sys.argv[2]},{sys.argv[3]})")
    elif cmd == "screenshot":
        path = pc.screenshot(sys.argv[2] if len(sys.argv) >= 3 else "")
        print(f"Screenshot: {path}")
    elif cmd == "url" and len(sys.argv) >= 3:
        ok = pc.open_url_in_tab(sys.argv[2])
        print(f"URL {'OK' if ok else 'ECHEC'}: {sys.argv[2]}")
    elif cmd == "tabs":
        for t in pc.chrome_tabs():
            print(f"  {t['title'][:60]} — {t['url'][:80]}")
    elif cmd == "processes":
        for p in pc.list_processes():
            if isinstance(p, dict):
                print(f"  [{p.get('Id','')}] {p.get('ProcessName',''):<25s} {p.get('MemMB',0):>8.1f} MB")
    elif cmd == "sysinfo":
        print(json.dumps(pc.system_info(), ensure_ascii=False, indent=2, default=str))
    elif cmd == "test":
        print("=== Test PC-Master ===\n")
        print("Fenetres:")
        wins = pc.list_windows()
        print(f"  {len(wins)} fenetres trouvees")
        print("\nFenetre active:")
        active = pc.get_active_window()
        print(f"  {active}")
        print("\nInfo systeme:")
        info = pc.system_info()
        print(f"  {info}")
        print("\nOnglets Chrome:")
        tabs = pc.chrome_tabs()
        print(f"  {len(tabs)} onglets")
        print("\n[OK] Test termine.")
    else:
        print(f"Commande inconnue: {cmd}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
