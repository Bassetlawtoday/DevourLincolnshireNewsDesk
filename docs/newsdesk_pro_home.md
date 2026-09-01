# NewsDesk Pro Home

> Architecture note: Home now reads stable module names and workload classes
> from `newsdesk.dashboard.registry`. Collection remains in
> `DashboardRefreshCoordinator`, full current-process payloads remain in
> `DashboardResultRepository`, and module windows retain their established
> public loading methods. See `02 System Architecture.md` and `04 Dashboard.md`.

NewsDesk Pro opens on the Devour Lincolnshire newsroom dashboard. The dashboard can refresh Planning, Police, Fire, Sport and the chronological Government / National feed while keeping the module windows independent.

Content is selected in its intelligence module and transferred to **Social Desk**
with **ADD TO SOCIALS**. Social Desk prepares local drafts for Metricool and never
publishes automatically. Direct Facebook collection and Facebook Operations are
not part of this newsroom build.

## Desktop shortcut

No packaged executable or PyInstaller specification currently exists in this repository. Once a packaged executable is available, create the shortcut without administrator rights:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_newsdesk_shortcut.ps1 -ExecutablePath "C:\Path\To\NewsDesk Pro.exe"
```

For an explicit development-only shortcut:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_newsdesk_shortcut.ps1 -Development -PythonPath "C:\Path\To\python.exe" -ProjectPath "C:\Path\To\DevourLincolnshireNewsDesk"
```

The development shortcut is deliberately named `NewsDesk Pro (Development)`. The setup script prompts before replacing a matching NewsDesk Pro shortcut and never changes unrelated shortcuts.

Remove the shortcut by deleting `NewsDesk Pro.lnk` (or `NewsDesk Pro (Development).lnk`) from the current user's Desktop. To change installation location, rerun the script with the new path and confirm replacement.

Packaging remains a separate future step because the project has no existing reliable packaging setup to update.
