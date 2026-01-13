# Backup script for Data Center News Chatbot
# Run this script regularly to backup your code

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$backupDir = ".\backups"
$backupName = "backup_$timestamp"

# Create backups directory if it doesn't exist
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

Write-Host "Creating backup: $backupName" -ForegroundColor Green

# Create backup directory
$fullBackupPath = Join-Path $backupDir $backupName
New-Item -ItemType Directory -Path $fullBackupPath | Out-Null

# Files and directories to backup (excluding sensitive/unnecessary files)
$itemsToBackup = @(
    "*.py",
    "requirements.txt",
    "README.md",
    "scheduler.py",
    "services",
    "scrapers",
    "database"
)

# Copy files
foreach ($item in $itemsToBackup) {
    $sourcePath = Join-Path "." $item
    if (Test-Path $sourcePath) {
        Write-Host "  Backing up: $item" -ForegroundColor Yellow
        Copy-Item -Path $sourcePath -Destination $fullBackupPath -Recurse -Force
    }
}

# Create a manifest file with backup info
$manifest = @"
Backup created: $timestamp
Source: $(Get-Location)
Files backed up:
$($itemsToBackup -join "`n")
"@

$manifest | Out-File -FilePath (Join-Path $fullBackupPath "BACKUP_INFO.txt") -Encoding UTF8

Write-Host "`nBackup completed successfully!" -ForegroundColor Green
Write-Host "Location: $fullBackupPath" -ForegroundColor Cyan

# Optional: Keep only last 10 backups
$backups = Get-ChildItem -Path $backupDir -Directory | Sort-Object CreationTime -Descending
if ($backups.Count -gt 10) {
    Write-Host "`nCleaning up old backups (keeping last 10)..." -ForegroundColor Yellow
    $backups | Select-Object -Skip 10 | Remove-Item -Recurse -Force
}
