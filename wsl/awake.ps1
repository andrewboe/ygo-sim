# Keep Windows from idle-sleeping while a simulator job runs in WSL.
# Uses SetThreadExecutionState (the per-process request media players use); nothing in the power
# settings changes, and the request ends when this script exits.
#
#   powershell -File wsl\awake.ps1 -Command "bash /mnt/c/.../wsl/chokepoint_batch.sh ..."   run and hold
#   powershell -File wsl\awake.ps1 -WaitFor "game.py"   hold while a matching WSL process is running
param(
    [string]$Command,
    [string]$WaitFor,
    [int]$PollSeconds = 60
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Awake {
    [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);
}
"@
$ES_CONTINUOUS = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]1

[Awake]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED) | Out-Null
try {
    if ($Command) {
        wsl -- bash -c $Command
    } elseif ($WaitFor) {
        do {
            Start-Sleep -Seconds $PollSeconds
            $running = wsl -- pgrep -f $WaitFor
        } while ($running)
    } else {
        Write-Error "pass -Command or -WaitFor"
    }
} finally {
    [Awake]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
}
