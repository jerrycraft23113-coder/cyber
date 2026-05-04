# Install Python via winget, then launch the watchdog
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements

# Refresh PATH so python.exe is visible without a new shell
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH", "User")

# Run the watchdog
python "C:\vanguard_duel\sandbox\watchdog.py"
