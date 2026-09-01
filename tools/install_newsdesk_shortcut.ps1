param(
    [string]$ExecutablePath,
    [switch]$Development,
    [switch]$Force,
    [string]$PythonPath,
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$desktop = [Environment]::GetFolderPath("Desktop")

if ($Development) {
    if (-not $PythonPath) {
        throw "Development mode requires -PythonPath."
    }
    $resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
    $pythonw = Join-Path (Split-Path -Parent $resolvedPython) "pythonw.exe"
    $target = if (Test-Path -LiteralPath $pythonw) { $pythonw } else { $resolvedPython }
    $project = (Resolve-Path -LiteralPath $ProjectPath).Path
    $shortcutName = "NewsDesk Pro (Development).lnk"
    $arguments = '"' + (Join-Path $project "app.py") + '"'
    $workingDirectory = $project
    $iconLocation = "$target,0"
} else {
    if (-not $ExecutablePath) {
        throw "Packaged mode requires -ExecutablePath."
    }
    $target = (Resolve-Path -LiteralPath $ExecutablePath).Path
    if ([IO.Path]::GetExtension($target) -ne ".exe") {
        throw "ExecutablePath must identify a packaged .exe file."
    }
    $shortcutName = "NewsDesk Pro.lnk"
    $arguments = ""
    $workingDirectory = Split-Path -Parent $target
    $iconLocation = "$target,0"
}

$shortcutPath = Join-Path $desktop $shortcutName
if ((Test-Path -LiteralPath $shortcutPath) -and -not $Force) {
    $answer = Read-Host "$shortcutName already exists. Replace it? (y/N)"
    if ($answer -notin @("y", "Y", "yes", "YES")) {
        Write-Host "Shortcut was not changed."
        exit 0
    }
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $workingDirectory
$shortcut.IconLocation = $iconLocation
$shortcut.Description = "Launch NewsDesk Pro"
$shortcut.Save()
Write-Host "Created $shortcutPath"
