<#
.SYNOPSIS
  Demo day in one command: robot over option A, host on the Pi, checks, console.

.DESCRIPTION
  On the Windows laptop that drives the robot, from the root of the repo:

      powershell -ExecutionPolicy Bypass -File scripts\demo.ps1             # everything
      powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Battery    # + battery voltage
      powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Status     # look only, change nothing

  Each step is skipped when already done, so running it again is safe (after a Pi reboot, too):
    1. The Pi: on "makai-kiwi" (option A) or on the iPhone hotspot. On the hotspot, it is
       switched to option A (asks the Pi password, for sudo). A rebooted Pi is always back on
       the hotspot: makai-ap never starts at boot.
    2. The laptop's Wi-Fi on "makai-kiwi" (asks the Wi-Fi password once, then Windows keeps it).
    3. An SSH key for the Pi (asks the Pi password once, on the first run on this laptop).
    4. The host running on the Pi, in tmux session "host" (log: ~/host.log on the Pi).
    5. configs/local.yaml (robot.remote_ip 10.42.0.1, stations kind pattern) and
       configs/zone.yaml (the demo arena, copied from configs/zone_demo.yaml).
    6. -Battery: the battery voltage. Pauses the host a few seconds: the arm goes limp.
    7. scripts/mission_check.py, then the console (scripts/drive.py --link host) in the browser.
       While it runs, the Wi-Fi is kept on makai-kiwi: Windows hops back to a network with
       internet when it can, and the robot stops when the link drops.

  Passwords (Pi, makai-kiwi): team chat, never in git.
  Needs: OpenSSH (built into Windows), and uv (or -Python <python.exe> with LeRobot installed).
#>
param(
    [switch]$Battery,     # read the battery voltage (pauses the host for a few seconds)
    [switch]$Status,      # report the state of everything, change nothing
    [switch]$SkipCheck,   # skip scripts/mission_check.py
    [string]$Python = ""  # a python.exe with LeRobot, instead of "uv run --no-sync python"
)

# Not "Stop": in Windows PowerShell 5.1 a native command writing to stderr (ssh, netsh) would
# then abort the script. Every step checks its own result instead.
$ErrorActionPreference = "Continue"
$Ssid = "makai-kiwi"
$PiAp = "10.42.0.1"
$PiUser = "kiwi"
$Ssh = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new", "-o", "LogLevel=ERROR")
Set-Location (Split-Path -Parent $PSScriptRoot)

function Say($text) { Write-Host "[demo] $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "[ ok ] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "[WARN] $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "[FAIL] $text" -ForegroundColor Red; exit 1 }

function Test-Port([string]$Ip, [int]$Port = 22, [int]$Ms = 600) {
    $client = New-Object Net.Sockets.TcpClient
    try { return ($client.ConnectAsync($Ip, $Port).Wait($Ms) -and $client.Connected) } catch { return $false } finally { $client.Close() }
}

function Get-WifiSsid {
    $line = netsh wlan show interfaces | Select-String -Pattern "^\s+SSID\s+:" | Select-Object -First 1
    if ($line) { return ($line.ToString() -split ":\s*", 2)[1].Trim() } else { return "" }
}

function Test-ApVisible { return [bool](netsh wlan show networks | Select-String -SimpleMatch $Ssid) }

function Find-PiOnHotspot {
    $mine = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object IPAddress)
    foreach ($n in 2..14) {
        $ip = "172.20.10.$n"
        if ($mine -notcontains $ip -and (Test-Port $ip)) { return $ip }
    }
    return $null
}

function Invoke-Pi([string]$Ip, [string]$Script) {
    # Runs a bash script on the Pi through stdin. Carriage returns are removed on the Pi's side:
    # this file may have Windows line ends, and PowerShell 5.1 adds one after what it pipes.
    $Script | & ssh @Ssh "$PiUser@$Ip" "tr -d '\r' | bash"
}

function Wait-For([scriptblock]$Condition, [int]$Seconds) {
    $end = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $end) { if (& $Condition) { return $true }; Start-Sleep -Milliseconds 1000 }
    return $false
}

function Connect-Ap {
    if ((Get-WifiSsid) -eq $Ssid -and (Test-Port $PiAp)) { Ok "laptop on $Ssid, Pi at $PiAp"; return }
    netsh wlan show profiles name="$Ssid" *> $null
    if ($LASTEXITCODE -ne 0) {
        $secure = Read-Host "Wi-Fi password of $Ssid (team chat)" -AsSecureString
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        $xml = Join-Path $env:TEMP "makai-kiwi-profile.xml"
        @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>$Ssid</name>
  <SSIDConfig><SSID><name>$Ssid</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security>
    <authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
    <sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>$plain</keyMaterial></sharedKey>
  </security></MSM>
</WLANProfile>
"@ | Set-Content -Path $xml -Encoding UTF8
        try { netsh wlan add profile filename="$xml" user=current | Out-Null } finally { Remove-Item $xml -Force }
    }
    Say "connecting the Wi-Fi to $Ssid (Windows will say 'no internet': normal)"
    $ok = Wait-For { netsh wlan connect name="$Ssid" ssid="$Ssid" | Out-Null; Start-Sleep 3; Test-Port $PiAp 22 1000 } 45
    if (-not $ok) { Fail "the Pi does not answer at $PiAp on $Ssid. Wrong Wi-Fi password? netsh wlan delete profile name=$Ssid, then run again" }
    Ok "laptop on $Ssid, Pi at $PiAp"
}

$HostScript = @'
cat > ~/start_host.sh <<'EOF'
#!/bin/bash
# Started by tmux session "host": the MAKAI host with both cameras (docs/SETUP.md, section 4).
source ~/miniforge3/etc/profile.d/conda.sh && conda activate lerobot && cd ~/lerobot
python ~/makai_host.py --arm_acceleration=50 \
  --robot.id=makai_kiwi --robot.port=/dev/ttyACM0 \
  --robot.cameras="{front: {type: opencv, index_or_path: /dev/video0, width: 640, height: 480, fps: 30, fourcc: MJPG, warmup_s: 3}, wrist: {type: opencv, index_or_path: /dev/video2, width: 640, height: 480, fps: 30, fourcc: MJPG, warmup_s: 3}}" \
  --host.connection_time_s=36000 2>&1 | tee ~/host.log
EOF
chmod +x ~/start_host.sh
'@

$BatteryScript = @'
cat > ~/read_battery.py <<'EOF'
"""Battery voltage from the wheel servos (ids 7-9). Run only while the host is stopped."""
from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

bus = FeetechMotorsBus(
    port="/dev/ttyACM0",
    motors={f"wheel_{i}": Motor(i, "sts3215", MotorNormMode.RANGE_M100_100) for i in (7, 8, 9)},
)
try:
    bus.connect()
    raw = bus.sync_read("Present_Voltage", normalize=False)
    print("BATTERY", " ".join(f"{v / 10:.1f}" for v in raw.values()))
finally:
    try:
        bus.disconnect(disable_torque=False)
    except Exception as e:
        print("disconnect:", e)
EOF
tmux kill-session -t host 2>/dev/null
for i in $(seq 1 25); do pgrep -f "[m]akai_host.py" >/dev/null || break; sleep 0.2; done
source ~/miniforge3/etc/profile.d/conda.sh && conda activate lerobot && python ~/read_battery.py 2>/dev/null | grep BATTERY
'@

# ---- 1. Where is the Pi? ------------------------------------------------------------------
Say "looking for the Pi"
$wifi = Get-WifiSsid
$apVisible = Test-ApVisible
$hotspotIp = $null
if ($wifi -eq $Ssid -and (Test-Port $PiAp)) { $where = "ap" }
elseif ($apVisible) { $where = "ap-visible" }
else {
    $hotspotIp = Find-PiOnHotspot
    $where = if ($hotspotIp) { "hotspot" } else { "none" }
}
switch ($where) {
    "ap" { Ok "Pi in option A, laptop already on $Ssid" }
    "ap-visible" { Ok "Pi in option A ($Ssid broadcasting), laptop on '$wifi'" }
    "hotspot" { Ok "Pi on the iPhone hotspot at $hotspotIp (option A is off: rebooted?)" }
    "none" {
        Fail ("Pi not found: not on $Ssid, not on the hotspot (laptop Wi-Fi: '$wifi'). Check: Pi LED green " +
            "(red = off: battery or USB-C), iPhone Personal Hotspot on with its screen open, " +
            "laptop on the hotspot. Then run again.")
    }
}

if ($Status) {
    if ($where -eq "ap") {
        $state = Invoke-Pi $PiAp "tmux has-session -t host 2>/dev/null && echo running || echo stopped; vcgencmd get_throttled"
        Say "host on the Pi: $($state -join ', ')"
    }
    Say "status only: nothing changed"
    exit 0
}

# ---- 2. Option A --------------------------------------------------------------------------
if ($where -eq "hotspot") {
    Say "SSH key and switch to option A, through the hotspot"
    if (-not (Test-Path "$HOME\.ssh\id_ed25519")) { ssh-keygen -t ed25519 -N '""' -C "makai-demo" -f "$HOME\.ssh\id_ed25519" -q }
    & ssh @Ssh "$PiUser@$hotspotIp" true 2>$null
    if ($LASTEXITCODE -ne 0) {
        Say "installing this laptop's SSH key on the Pi: type the Pi password (team chat)"
        Get-Content "$HOME\.ssh\id_ed25519.pub" | ssh -o StrictHostKeyChecking=accept-new "$PiUser@$hotspotIp" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && tr -d '\r' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
    }
    Say "switching the Pi to option A: type the Pi password if sudo asks for it"
    ssh -t -o StrictHostKeyChecking=accept-new "$PiUser@$hotspotIp" "sudo sh -c 'nohup nmcli connection up makai-ap >/tmp/makai-ap.log 2>&1 &'"
    if (-not (Wait-For { Test-ApVisible } 60)) { Fail "$Ssid does not appear after 60 s: power-cycle the Pi and run again" }
    Ok "$Ssid is broadcasting"
}
Connect-Ap

# ---- 3. SSH key (first run on this laptop) --------------------------------------------------
if (-not (Test-Path "$HOME\.ssh\id_ed25519")) { ssh-keygen -t ed25519 -N '""' -C "makai-demo" -f "$HOME\.ssh\id_ed25519" -q }
& ssh @Ssh "$PiUser@$PiAp" true 2>$null
if ($LASTEXITCODE -ne 0) {
    Say "installing this laptop's SSH key on the Pi: type the Pi password (team chat)"
    Get-Content "$HOME\.ssh\id_ed25519.pub" | ssh -o StrictHostKeyChecking=accept-new "$PiUser@$PiAp" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && tr -d '\r' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
    & ssh @Ssh "$PiUser@$PiAp" true 2>$null
    if ($LASTEXITCODE -ne 0) { Fail "SSH to the Pi still asks for a password: wrong password?" }
}
Ok "SSH to the Pi without password"

# ---- 4. Battery (optional), then the host ---------------------------------------------------
if ($Battery) {
    Warn "reading the battery: the host stops a few seconds, the arm goes limp"
    $line = Invoke-Pi $PiAp ($BatteryScript)
    if ($line -match "BATTERY\s+([\d.]+)") {
        $v = [double]$Matches[1]
        $verdict = if ($v -ge 12.4) { "full" } elseif ($v -ge 11.5) { "fine for tests" } elseif ($v -ge 10.8) { "low: charge before the mission" } else { "nearly empty: CHARGE NOW (the Pi cuts out)" }
        if ($v -ge 11.5) { Ok "battery $v V: $verdict" } else { Warn "battery $v V: $verdict" }
    } else { Warn "battery not read: $line" }
}
$hostState = Invoke-Pi $PiAp "tmux has-session -t host 2>/dev/null && echo running || echo stopped"
if ($hostState -match "running") { Ok "host already running on the Pi" }
else {
    Say "starting the host on the Pi (tmux session 'host')"
    Invoke-Pi $PiAp ($HostScript + "`ntmux new -d -s host ~/start_host.sh") | Out-Null
    $ready = Wait-For { (Invoke-Pi $PiAp "tail -n 3 ~/host.log 2>/dev/null") -match "No command|Traceback|Error" } 40
    $tail = Invoke-Pi $PiAp "tail -n 3 ~/host.log 2>/dev/null"
    if ($tail -match "Traceback|Error") { Fail "the host failed on the Pi: $($tail -join ' | ')  (ssh $PiUser@$PiAp, then: tmux attach -t host)" }
    if ($ready) { Ok "host running" } else { Warn "host started, no output yet: check the console's camera images" }
}

# ---- 5. Laptop config ------------------------------------------------------------------------
if ($Python) { $Py = @($Python) } else {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail "uv not found: install it, or give -Python <python.exe with LeRobot>" }
    $Py = @("uv", "run", "--no-sync", "python")
}
# A simple function on purpose: $args keeps "-c" and "--link" as they are.
function Invoke-Py { $exe, $rest = $Py; & $exe @(@($rest) + $args | Where-Object { $_ -ne $null }) }

if (-not (Test-Path "configs\local.yaml")) {
    "robot:`n  remote_ip: $PiAp`nperception:`n  stations:`n    kind: pattern`n" | Set-Content -Path "configs\local.yaml" -Encoding ASCII
    Ok "configs/local.yaml created"
}
if (-not (Test-Path "configs\zone.yaml")) { Copy-Item "configs\zone_demo.yaml" "configs\zone.yaml"; Ok "configs/zone.yaml = the demo arena" }
$cfg = Invoke-Py -c "from makai.config import load_config as l; c=l(); print(c['robot']['remote_ip'], c['perception']['stations']['kind'])"
if ("$cfg" -notmatch [regex]::Escape($PiAp)) { Fail "robot.remote_ip is '$cfg' : set 'remote_ip: $PiAp' under 'robot:' in configs/local.yaml" }
if ("$cfg" -notmatch "pattern") { Warn "stations kind is not 'pattern' ($cfg): the bin's U will not be seen. Add under perception: stations: kind: pattern" }
Ok "config: robot at $PiAp, stations '$((("$cfg") -split ' ')[1])'"

# ---- 6. Check, then the console --------------------------------------------------------------
if (-not $SkipCheck) {
    Say "pre-robot check (scripts/mission_check.py)"
    Invoke-Py scripts\mission_check.py
    if ($LASTEXITCODE -ne 0) { Fail "mission_check failed: see above (models in outputs/train? docs/CE_SOIR.md)" }
}

$watchdog = Start-Job -ArgumentList $Ssid -ScriptBlock {
    param($ssid)
    while ($true) {
        $line = netsh wlan show interfaces | Select-String -Pattern "^\s+SSID\s+:" | Select-Object -First 1
        if (-not $line -or -not $line.ToString().Contains($ssid)) { netsh wlan connect name="$ssid" ssid="$ssid" | Out-Null }
        Start-Sleep -Seconds 3
    }
}
Say "console: http://localhost:8000  (Mission tab; the red STOP or the space bar stops everything; Ctrl+C here ends)"
Start-Job -ScriptBlock { Start-Sleep 6; Start-Process "http://localhost:8000" } | Out-Null
try { Invoke-Py scripts\drive.py --link host }
finally { Stop-Job $watchdog -ErrorAction SilentlyContinue; Remove-Job $watchdog -Force -ErrorAction SilentlyContinue; Say "console closed; the host keeps running on the Pi" }
