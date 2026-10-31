<#
.SYNOPSIS
    Launch Isaac Sim on Windows with the isaac.sim.mcp_extension enabled.

.DESCRIPTION
    Windows counterpart to scripts/run_isaac_sim.sh. Resolves the Isaac Sim
    launcher for the requested physics engine, verifies the extension manifest
    is present, then starts Isaac Sim with this repo registered as an extension
    search folder.

    The MCP extension opens a TCP socket (default localhost:8766) that the
    isaacsim-mcp-server process connects to. Because that socket accepts
    arbitrary Python via the execute_script command, it is bound to localhost
    and must never be exposed to another host.

.PARAMETER IsaacSimRoot
    Directory containing the Isaac Sim launcher (isaac-sim.bat). Defaults to
    $env:ISAACSIM_ROOT, then the local source build at
    <repo>/../IsaacSim/_build/windows-x86_64/release, then C:\isaacsim, then
    $env:USERPROFILE\isaacsim.

.PARAMETER Engine
    Physics engine: physx (default) or newton. Selects isaac-sim.bat vs
    isaac-sim.newton.bat. Overridable with $env:ISAACSIM_ENGINE or the
    --physx / --newton / --engine <name> flags (later wins), matching
    run_isaac_sim.sh. Newton ships with Isaac Sim 6.0 and later.

.PARAMETER Port
    TCP port for the extension socket. Defaults to $env:ISAAC_MCP_PORT or 8766.

.PARAMETER ExtraArgs
    Any remaining arguments are forwarded verbatim to the launcher. Engine
    selectors (--physx / --newton / --engine) are consumed here, not forwarded.
    --live-view turns on the browser live view (or set $env:ISAAC_LIVE_VIEW=1).

.EXAMPLE
    .\run_isaac_sim.ps1

.EXAMPLE
    .\run_isaac_sim.ps1 -Engine newton

.EXAMPLE
    .\run_isaac_sim.ps1 -Port 8767 -- --no-window
#>
[CmdletBinding()]
param(
    [string] $IsaacSimRoot,
    [string] $Engine,
    [int]    $Port,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot     = Split-Path -Parent $PSScriptRoot
$extensionId  = 'isaac.sim.mcp_extension'
$manifestPath = Join-Path $repoRoot "$extensionId\config\extension.toml"

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Extension manifest not found at: $manifestPath`nRun this script from inside the isaacsim-mcp-server checkout."
}

if (-not $Port) {
    $Port = if ($env:ISAAC_MCP_PORT) { [int] $env:ISAAC_MCP_PORT } else { 8766 }
}

# Engine name -> launcher shipped in the Isaac Sim install root. Mirrors
# scripts/lib/isaac_launcher.sh: add one entry to support a new engine.
$engineLaunchers = @{
    physx  = 'isaac-sim.bat'
    newton = 'isaac-sim.newton.bat'
}
$defaultEngine = 'physx'

# Selection order (later wins): default, $env:ISAACSIM_ENGINE, -Engine, then
# --engine <name> / --engine=<name> / --<name> on the command line.
# NOTE: the working variable must not be named $engine -- PowerShell variable
# names are case-insensitive, so $engine and the -Engine parameter alias the
# same storage and the default would silently clobber the parameter's value.
$selectedEngine = $defaultEngine
if ($env:ISAACSIM_ENGINE) { $selectedEngine = $env:ISAACSIM_ENGINE }
if ($Engine)              { $selectedEngine = $Engine }

# $ExtraArgs is $null (not an empty array) when nothing trails the named
# parameters; guard before indexing so Set-StrictMode does not trip on .Count.
$passthru = @()
if ($ExtraArgs) {
    for ($i = 0; $i -lt $ExtraArgs.Count; $i++) {
        $arg = $ExtraArgs[$i]
        if ($arg -eq '--') {
            continue
        } elseif ($arg -eq '--engine') {
            $selectedEngine = $ExtraArgs[$i + 1]; $i++
        } elseif ($arg -like '--engine=*') {
            $selectedEngine = $arg.Split('=', 2)[1]
        } elseif ($arg -eq '--live-view') {
            # The Kit setting the extension reads. Mirrors scripts/lib/isaac_launcher.sh.
            $passthru += '--/exts/isaac.sim.mcp_extension/live_view/enabled=true'
        } elseif ($arg -like '--*' -and $engineLaunchers.ContainsKey($arg.Substring(2))) {
            # --physx / --newton are engine selectors; every other flag is Kit's.
            $selectedEngine = $arg.Substring(2)
        } else {
            $passthru += $arg
        }
    }
}

if (-not $engineLaunchers.ContainsKey($selectedEngine)) {
    throw "Unknown physics engine '$selectedEngine'. Known engines: $($engineLaunchers.Keys -join ', ')"
}
$launcherName = $engineLaunchers[$selectedEngine]

# Resolve the Isaac Sim install. An explicit root (-IsaacSimRoot, else
# $env:ISAACSIM_ROOT) is authoritative: it is the ONLY candidate, so a wrong or
# engine-incompatible root fails loudly here instead of silently falling through
# to a different install (e.g. asking for Newton against a 5.1 root must not
# resolve to a 6.0 install elsewhere). Only when no root is given do we
# auto-discover: local source build, the default installer path, the home install.
if ($IsaacSimRoot) {
    $candidates = @($IsaacSimRoot)
} elseif ($env:ISAACSIM_ROOT) {
    $candidates = @($env:ISAACSIM_ROOT)
} else {
    $candidates = @(
        (Join-Path $repoRoot '..\IsaacSim\_build\windows-x86_64\release')
        'C:\isaacsim'
        (Join-Path $env:USERPROFILE 'isaacsim')
    )
}

$launcher = $null
foreach ($candidate in $candidates) {
    if (-not $candidate) { continue }
    $resolved = Join-Path $candidate $launcherName
    if (Test-Path -LiteralPath $resolved) {
        $launcher = (Resolve-Path -LiteralPath $resolved).Path
        break
    }
}

if (-not $launcher) {
    $hint = if ($selectedEngine -ne 'physx') {
        "`nThe '$selectedEngine' engine ships with Isaac Sim 6.0 and later; this install may be older."
    } else { '' }
    throw @"
Isaac Sim launcher ($launcherName) not found. Checked:
$($candidates -join "`n")
$hint
Set ISAACSIM_ROOT to your Isaac Sim directory, or pass -IsaacSimRoot.
"@
}

# Warn early instead of letting the extension fail to bind inside Isaac Sim.
function Test-PortInUse {
    param([int] $ProbePort)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync('127.0.0.1', $ProbePort).Wait(300)
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

if (Test-PortInUse -ProbePort $Port) {
    Write-Warning "Port $Port already has a listener. The MCP extension will fail to bind. Use -Port to pick another, and set ISAAC_MCP_PORT to match for the MCP server."
}

# Give USD/3D-generation helpers a writable working dir on Windows.
if (-not $env:USD_WORKING_DIR) {
    $env:USD_WORKING_DIR = Join-Path $repoRoot '.cache\usd'
}
New-Item -ItemType Directory -Path $env:USD_WORKING_DIR -Force | Out-Null

Write-Host "Repo root:   $repoRoot"
Write-Host "Isaac Sim:   $launcher"
Write-Host "Engine:      $selectedEngine"
Write-Host "Extension:   $extensionId"
Write-Host "MCP port:    $Port (localhost only)"
Write-Host "USD workdir: $env:USD_WORKING_DIR"
Write-Host ''

# The bare Linux launcher (run_isaac_sim.sh) does NOT set the port -- it leaves
# it to the manifest/defaults, and launch_isaac_sim_mcp.sh is what injects
# --/exts/.../server.port. There is no launch_isaac_sim_mcp.ps1, so this script
# folds the -Port handling in here. The extension reads this legacy prefix first
# (see _resolve_endpoint), so it wins over the manifest.
$argList = @(
    '--ext-folder', $repoRoot
    '--enable',     $extensionId
    "--/exts/isaac.sim.mcp/server.port=$Port"
    '--/exts/isaac.sim.mcp/server.host=localhost'
)
if ($passthru) {
    $argList += $passthru
}

& $launcher @argList
exit $LASTEXITCODE
