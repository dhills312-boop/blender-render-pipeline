param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$IdentityFile = "$env:USERPROFILE\.ssh\id_ed25519",

    [string]$BlendFile = "blender-output/lift-off/LO_083_spiderverse_downloaded_recipe.blend",

    [string]$RenderScript = "render_still.py",

    [string]$ConfigFile = "render_config.json",

    [string]$RemoteProjectDir = "/workspace/project",

    [string]$RemoteScriptsDir = "/workspace/render-scripts",

    [string]$RemoteOutputDir = "/workspace/output",

    [string]$LocalRendersDir = "$(Split-Path -Parent $PSScriptRoot)\renders"
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$ProjectDir = Join-Path $RootDir "workspace\project"
$ScriptsDir = Join-Path $RootDir "scripts"
$LocalRendersDir = [System.IO.Path]::GetFullPath($LocalRendersDir)

function Invoke-Checked {
    param([string[]]$Command)
    & $Command[0] $Command[1..($Command.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Command -join ' ')"
    }
}

if (-not (Test-Path $ProjectDir)) {
    throw "Project dir not found: $ProjectDir"
}
if (-not (Test-Path $ScriptsDir)) {
    throw "Scripts dir not found: $ScriptsDir"
}

New-Item -ItemType Directory -Force -Path $LocalRendersDir | Out-Null

$SshBase = @("ssh", "-i", $IdentityFile, "-o", "StrictHostKeyChecking=accept-new", $HostName)

Write-Host "[render-remote-tar] Checking remote tools"
Invoke-Checked ($SshBase + @("command -v blender && command -v tar && mkdir -p '$RemoteProjectDir' '$RemoteScriptsDir' '$RemoteOutputDir'"))

Write-Host "[render-remote-tar] Uploading project with tar over ssh"
tar -C $ProjectDir -czf - . | & ssh -i $IdentityFile -o StrictHostKeyChecking=accept-new $HostName "rm -rf '$RemoteProjectDir' && mkdir -p '$RemoteProjectDir' && tar -xzf - -C '$RemoteProjectDir'"
if ($LASTEXITCODE -ne 0) {
    throw "Project upload failed"
}

Write-Host "[render-remote-tar] Uploading render scripts with tar over ssh"
tar -C $ScriptsDir -czf - . | & ssh -i $IdentityFile -o StrictHostKeyChecking=accept-new $HostName "rm -rf '$RemoteScriptsDir' && mkdir -p '$RemoteScriptsDir' && tar -xzf - -C '$RemoteScriptsDir'"
if ($LASTEXITCODE -ne 0) {
    throw "Render script upload failed"
}

$RemoteBlend = "$RemoteProjectDir/$BlendFile"
$RemoteScript = "$RemoteScriptsDir/$RenderScript"
$RemoteConfig = "$RemoteScriptsDir/$ConfigFile"

Write-Host "[render-remote-tar] Rendering $RemoteBlend"
$RenderCommand = "cd '$RemoteProjectDir' && blender -b '$RemoteBlend' -P '$RemoteScript' -- --config '$RemoteConfig' --blend-file '$RemoteBlend'"
Invoke-Checked ($SshBase + @($RenderCommand))

Write-Host "[render-remote-tar] Pulling renders to $LocalRendersDir"
& ssh -i $IdentityFile -o StrictHostKeyChecking=accept-new $HostName "cd '$RemoteOutputDir' && tar -czf - ." | tar -xzf - -C $LocalRendersDir
if ($LASTEXITCODE -ne 0) {
    throw "Render pull failed"
}

Write-Host "[render-remote-tar] Done"
