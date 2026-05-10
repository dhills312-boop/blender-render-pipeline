param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$IdentityFile = "$env:USERPROFILE\.ssh\id_ed25519",

    [Parameter(Mandatory = $true)]
    [string]$BlendFile,

    [Parameter(Mandatory = $true)]
    [string]$BlenderScript,

    [string[]]$ScriptArgs = @(),

    [string]$RemoteProjectDir = "/workspace/project",

    [string]$RemoteScriptsDir = "/workspace/render-scripts",

    [string]$RemoteAssetDir = "/workspace/Asset_Addon_Library",

    [switch]$IncludeAssetLibrary
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$ProjectDir = Join-Path $RootDir "workspace\project"
$ScriptsDir = Join-Path $RootDir "scripts"
$AssetDir = Join-Path $RootDir "Asset_Addon_Library"

function Invoke-Checked {
    param([string[]]$Command)
    & $Command[0] $Command[1..($Command.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Command -join ' ')"
    }
}

function Quote-Remote {
    param([string]$Value)
    return "'" + ($Value -replace "'", "'\''") + "'"
}

if (-not (Test-Path $ProjectDir)) {
    throw "Project dir not found: $ProjectDir"
}
if (-not (Test-Path $ScriptsDir)) {
    throw "Scripts dir not found: $ScriptsDir"
}
if ($IncludeAssetLibrary -and -not (Test-Path $AssetDir)) {
    throw "Asset library dir not found: $AssetDir"
}

$SshBase = @("ssh", "-i", $IdentityFile, "-o", "StrictHostKeyChecking=accept-new", $HostName)

Write-Host "[run-blender-script-tar] Checking remote tools"
Invoke-Checked ($SshBase + @("command -v blender && command -v tar && mkdir -p '$RemoteProjectDir' '$RemoteScriptsDir'"))

Write-Host "[run-blender-script-tar] Uploading project"
tar -C $ProjectDir -czf - . | & ssh -i $IdentityFile -o StrictHostKeyChecking=accept-new $HostName "rm -rf '$RemoteProjectDir' && mkdir -p '$RemoteProjectDir' && tar -xzf - -C '$RemoteProjectDir'"
if ($LASTEXITCODE -ne 0) {
    throw "Project upload failed"
}

Write-Host "[run-blender-script-tar] Uploading scripts"
tar -C $ScriptsDir -czf - . | & ssh -i $IdentityFile -o StrictHostKeyChecking=accept-new $HostName "rm -rf '$RemoteScriptsDir' && mkdir -p '$RemoteScriptsDir' && tar -xzf - -C '$RemoteScriptsDir'"
if ($LASTEXITCODE -ne 0) {
    throw "Script upload failed"
}

if ($IncludeAssetLibrary) {
    Write-Host "[run-blender-script-tar] Uploading asset library"
    tar -C $AssetDir -czf - . | & ssh -i $IdentityFile -o StrictHostKeyChecking=accept-new $HostName "rm -rf '$RemoteAssetDir' && mkdir -p '$RemoteAssetDir' && tar -xzf - -C '$RemoteAssetDir'"
    if ($LASTEXITCODE -ne 0) {
        throw "Asset library upload failed"
    }
}

$RemoteBlend = "$RemoteProjectDir/$BlendFile"
$RemoteScript = "$RemoteScriptsDir/$BlenderScript"
$QuotedArgs = ($ScriptArgs | ForEach-Object { Quote-Remote $_ }) -join " "
$RunCommand = "cd '$RemoteProjectDir' && blender -b '$RemoteBlend' -P '$RemoteScript' -- $QuotedArgs"

Write-Host "[run-blender-script-tar] Running $RemoteScript on $RemoteBlend"
Invoke-Checked ($SshBase + @($RunCommand))

Write-Host "[run-blender-script-tar] Pulling project updates"
& ssh -i $IdentityFile -o StrictHostKeyChecking=accept-new $HostName "cd '$RemoteProjectDir' && tar -czf - ." | tar -xzf - -C $ProjectDir
if ($LASTEXITCODE -ne 0) {
    throw "Project pull failed"
}

Write-Host "[run-blender-script-tar] Done"
