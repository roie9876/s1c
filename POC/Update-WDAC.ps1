# Script to whitelist Check Point SmartConsole in WDAC
# Run as Administrator

$ErrorActionPreference = "Stop"

$SmartConsolePath = "C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM"
$TempDir = "C:\Temp\WDAC_SmartConsole"
$PolicyXml = "$TempDir\SmartConsoleAllow.xml"
$PolicyBin = "$TempDir\SmartConsoleAllow.cip"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   WDAC Policy Updater for SmartConsole   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Check Prerequisites
if (-not (Test-Path $SmartConsolePath)) {
    Write-Error "SmartConsole directory not found at: $SmartConsolePath"
    exit 1
}

if (-not (Get-Command New-CIPolicy -ErrorAction SilentlyContinue)) {
    Write-Error "ConfigCI module not found. Ensure you are running on Windows Enterprise/Pro and have the feature enabled."
    exit 1
}

# 2. Create Temp Directory
if (-not (Test-Path $TempDir)) {
    New-Item -Path $TempDir -ItemType Directory -Force | Out-Null
}

Write-Host "[1/4] Scanning SmartConsole directory for signatures..." -ForegroundColor Cyan
Write-Host "      Path: $SmartConsolePath"
Write-Host "      This may take a minute..."

# 3. Create Policy (Publisher Level)
# We use -UserPEs to include user-mode executables
# -Level Publisher trusts the certificate (Check Point Software Technologies Ltd.)
New-CIPolicy -Level Publisher -Fallback Hash -UserPEs -ScanPath $SmartConsolePath -FilePath $PolicyXml

Write-Host "[2/4] Converting policy to binary..." -ForegroundColor Cyan
ConvertFrom-CIPolicy -XmlFilePath $PolicyXml -BinaryFilePath $PolicyBin

Write-Host "[3/4] Attempting to apply policy..." -ForegroundColor Cyan

# 4. Apply Policy
if (Get-Command CiTool -ErrorAction SilentlyContinue) {
    Write-Host "      Using CiTool to update policy..."
    CiTool --update-policy $PolicyBin
    Write-Host "[SUCCESS] Policy updated successfully via CiTool." -ForegroundColor Green
}
else {
    Write-Host "[WARNING] CiTool not found. You must manually copy the policy." -ForegroundColor Yellow
    
    # Extract GUID from XML to name the file correctly for the Active folder
    [xml]$xml = Get-Content $PolicyXml
    $PolicyID = $xml.SiPolicy.PolicyID
    $DestPath = "C:\Windows\System32\CodeIntegrity\CiPolicies\Active\{$PolicyID}.cip"
    
    Write-Host "      Policy ID: $PolicyID"
    Write-Host "      Destination: $DestPath"
    
    try {
        if (-not (Test-Path "C:\Windows\System32\CodeIntegrity\CiPolicies\Active")) {
             New-Item -Path "C:\Windows\System32\CodeIntegrity\CiPolicies\Active" -ItemType Directory -Force | Out-Null
        }
        Copy-Item -Path $PolicyBin -Destination $DestPath -Force
        Write-Host "[SUCCESS] Policy copied to Active folder. A reboot may be required." -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to copy policy file. Ensure you are running as Administrator."
    }
}

Write-Host "`nDone. Please try running the SmartConsole Launcher again." -ForegroundColor Green
