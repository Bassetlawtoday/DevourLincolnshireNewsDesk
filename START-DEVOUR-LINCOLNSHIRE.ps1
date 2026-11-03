$ErrorActionPreference = "Stop"

$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectPath ".venv\Scripts\pythonw.exe"
$Application = Join-Path $ProjectPath "app.py"

if (-not (Test-Path $Python)) {
    Add-Type -AssemblyName PresentationFramework

    [System.Windows.MessageBox]::Show(
        "The NewsDesk Python environment was not found.",
        "Devour Lincolnshire NewsDesk",
        "OK",
        "Error"
    ) | Out-Null

    exit 1
}

if (-not (Test-Path $Application)) {
    Add-Type -AssemblyName PresentationFramework

    [System.Windows.MessageBox]::Show(
        "The NewsDesk application was not found.",
        "Devour Lincolnshire NewsDesk",
        "OK",
        "Error"
    ) | Out-Null

    exit 1
}

Start-Process `
    -FilePath $Python `
    -ArgumentList "`"$Application`"" `
    -WorkingDirectory $ProjectPath
