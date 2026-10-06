# Fit the game evaluation from outcomes, iteratively (THEORY §5.1): play games -> fit -> play with the
# fitted weights -> refit. Holds Windows awake for the whole loop (see awake.ps1).
#
#   powershell -File wsl\eval_loop.ps1 -First elfnote__tcg -Second elfnote__tcg -Rounds 3 -Games 60
param(
    [string]$First = "elfnote__tcg",
    [string]$Second = "elfnote__tcg",
    [int]$Rounds = 3,
    [int]$Games = 60,
    [int]$MaxTurns = 8
)
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "data\games\eval_loop.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Awake2 {
    [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);
}
"@
[Awake2]::SetThreadExecutionState([uint32]2147483648 -bor [uint32]1) | Out-Null
try {
    for ($r = 0; $r -lt $Rounds; $r++) {
        "== round $r: $Games games ($First first vs $Second)" | Tee-Object -Append $log
        $cmd = "TIMEOUT=14400 bash /mnt/c/Users/andre/Desktop/ygo-sim/wsl/run_py.sh game.py $First $Second " +
               "--games $Games --max-turns $MaxTurns --first-game $($r * $Games)"
        wsl -- bash -c $cmd 2>&1 | Select-String -Pattern "eval weights|first wins|games in" | ForEach-Object { $_.Line } |
            Tee-Object -Append $log
        & (Join-Path $root ".venv\Scripts\ygosim.exe") fit-eval 2>&1 | Tee-Object -Append $log
    }
    "== done" | Tee-Object -Append $log
} finally {
    [Awake2]::SetThreadExecutionState([uint32]2147483648) | Out-Null
}
