# PowerShell Script to Register MusicPlayer Protocol Handler for Current User

# --- Configuration ---
$ProtocolName = "musicplayerdl"
# IMPORTANT: Use the absolute path to where MusicPlayer.exe will be located
# Ensure this path reflects the final build location within the 'dist' subfolder.
$ExecutablePath = "D:\projects\musicplayer\dist\MusicPlayer.exe" # Using double backslashes in PS string
$ProtocolDescription = "URL:MusicPlayer Protocol"

# --- Registry Paths ---
$BaseRegPath = "HKCU:\Software\Classes\$ProtocolName" # Using HKCU for current user, no admin needed
$CommandRegPath = "$BaseRegPath\shell\open\command"
$IconRegPath = "$BaseRegPath\DefaultIcon"

# --- Script Logic ---

# Check if the executable path exists (optional, but good practice)
$ExecutableDir = Split-Path $ExecutablePath -Parent
if (-not (Test-Path $ExecutableDir -PathType Container)) {
    Write-Warning "Target directory for executable not found: $ExecutableDir"
    Write-Warning "Attempting to create registry keys anyway."
    # Optionally, create the directory:
    # try {
    #     New-Item -Path $ExecutableDir -ItemType Directory -Force -ErrorAction Stop
    #     Write-Host "Created target directory: $ExecutableDir"
    # } catch {
    #     Write-Error "Failed to create target directory: $_"
    #     exit 1
    # }
} elseif (-not (Test-Path $ExecutablePath -PathType Leaf)) {
    Write-Warning "Executable not found at specified path: $ExecutablePath"
    Write-Warning "Registry keys will be created, but the handler may not function until the executable exists."
}

Write-Host "Registering protocol handler '$ProtocolName' for the current user..."

# Create the base protocol key
if (-not (Test-Path $BaseRegPath)) {
    try {
        New-Item -Path $BaseRegPath -Force -ErrorAction Stop | Out-Null
        Write-Host "Created base key: $BaseRegPath"
    } catch {
        Write-Error "Failed to create base registry key: $_"
        exit 1
    }
} else {
    Write-Host "Base key already exists: $BaseRegPath"
}

# Set protocol description and URL Protocol identifier
try {
    Set-ItemProperty -Path $BaseRegPath -Name '(Default)' -Value $ProtocolDescription -Force -ErrorAction Stop | Out-Null
    Set-ItemProperty -Path $BaseRegPath -Name 'URL Protocol' -Value '' -Force -ErrorAction Stop | Out-Null # Indicates it's a URL protocol
} catch {
    Write-Error "Failed to set base key properties: $_"
    exit 1
}

# Set the default icon for the protocol
if (-not (Test-Path $IconRegPath)) {
    try {
        New-Item -Path $IconRegPath -Force -ErrorAction Stop | Out-Null
    } catch {
        Write-Error "Failed to create icon registry key: $_"
        # Continue even if icon fails, not critical
    }
}

# Set the icon to the executable itself (if it exists)
if (Test-Path $ExecutablePath -PathType Leaf) {
    try {
        Set-ItemProperty -Path $IconRegPath -Name '(Default)' -Value "$ExecutablePath,0" -Force -ErrorAction Stop | Out-Null # ',0' specifies the first icon in the exe
    } catch {
        Write-Warning "Failed to set icon registry property: $_"
        # Continue even if icon fails
    }
} else {
    Write-Warning "Executable not found at $ExecutablePath, skipping icon setting."
}


# Create the necessary shell\open\command keys
if (-not (Test-Path $CommandRegPath)) {
    try {
        # Create intermediate keys if they don't exist
        $ShellRegPath = Split-Path $CommandRegPath -Parent
        $OpenRegPath = Split-Path $ShellRegPath -Parent
        # Ensure correct structure: HKCU:\Software\Classes\$ProtocolName\shell\open\command
        if (-not (Test-Path $OpenRegPath)) { New-Item -Path $OpenRegPath -Force -ErrorAction Stop | Out-Null }
        if (-not (Test-Path $ShellRegPath)) { New-Item -Path $ShellRegPath -Force -ErrorAction Stop | Out-Null }
        New-Item -Path $CommandRegPath -Force -ErrorAction Stop | Out-Null
        Write-Host "Created command key path: $CommandRegPath"
    } catch {
        Write-Error "Failed to create command registry key path: $_"
        exit 1
    }
} else {
     Write-Host "Command key path already exists: $CommandRegPath"
}

# Set the command to execute (Executable path followed by "%1" which represents the URL)
# Crucially, %1 must be enclosed in its own quotes for URLs with spaces/special chars
$CommandValue = "`"$ExecutablePath`" `"%1`"" # Format: "C:\path\to\exe.exe" "%1"
try {
    Set-ItemProperty -Path $CommandRegPath -Name '(Default)' -Value $CommandValue -Force -ErrorAction Stop | Out-Null
} catch {
    Write-Error "Failed to set command registry property: $_"
    exit 1
}

Write-Host "Successfully registered '$ProtocolName' protocol handler for the current user."
Write-Host "Associated Command: $CommandValue"

# Optional: Pause at the end when run directly
# if ($Host.Name -eq 'ConsoleHost') {
#     Write-Host "Press Enter to exit..."
#     Read-Host
# }

exit 0
