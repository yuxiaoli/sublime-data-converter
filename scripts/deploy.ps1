<#
.SYNOPSIS
  Deploy the data-converter plugin into the local Sublime Text Packages folder.

.DESCRIPTION
  Copies (or symlinks) the plugin sources into:
    %APPDATA%\Sublime Text\Packages\DataConverter

  Excludes development-only files (.git, .venv, tests, src, temp, logs, etc.).

.PARAMETER PackagesDir
  Override the destination Packages directory. Defaults to:
    "$env:APPDATA\Sublime Text\Packages"
  (falls back to "Sublime Text 3" if "Sublime Text" is missing).

.PARAMETER PackageName
  Folder name created under Packages. Default: "DataConverter".

.PARAMETER Symlink
  Create a directory junction instead of copying. Useful for live development.
  Removes any existing destination first.

.PARAMETER Force
  Overwrite the destination even if it already exists.

.EXAMPLE
  .\scripts\deploy.ps1
  .\scripts\deploy.ps1 -Symlink
  .\scripts\deploy.ps1 -PackagesDir "D:\Portable\SublimeText\Data\Packages"
#>
[CmdletBinding()]
param(
    [string]$PackagesDir,
    [string]$PackageName = "DataConverter",
    [switch]$Symlink,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Resolve-PackagesDir {
    param([string]$Override)
    if ($Override) { return $Override }
    $candidates = @(
        (Join-Path $env:APPDATA "Sublime Text\Packages"),
        (Join-Path $env:APPDATA "Sublime Text 3\Packages")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    # Default to ST4 location even if missing; we will create it.
    return $candidates[0]
}

$Dest = Join-Path (Resolve-PackagesDir -Override $PackagesDir) $PackageName

Write-Host "Source     : $ProjectRoot"
Write-Host "Destination: $Dest"
Write-Host "Mode       : $(if ($Symlink) { 'symlink (junction)' } else { 'copy' })"

if (Test-Path $Dest) {
    Write-Host "Removing existing destination..."
    Remove-Item -Recurse -Force $Dest
}

$parent = Split-Path -Parent $Dest
if (-not (Test-Path $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

if ($Symlink) {
    # Directory junction works without admin on NTFS.
    New-Item -ItemType Junction -Path $Dest -Target $ProjectRoot | Out-Null
    Write-Host "Created junction $Dest -> $ProjectRoot"
    exit 0
}

# File-copy mode: only ship the files the plugin actually needs at runtime.
$Includes = @(
    "data_converter.py",
    "lib",
    "Default.sublime-commands",
    "dependencies.json",
    ".python-version",
    "README.md",
    "LICENSE"
)

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

foreach ($name in $Includes) {
    $src = Join-Path $ProjectRoot $name
    if (-not (Test-Path $src)) { continue }
    $dst = Join-Path $Dest $name
    if ((Get-Item $src).PSIsContainer) {
        Copy-Item -Recurse -Force -Path $src -Destination $dst
        # Strip __pycache__ inside copied folder.
        Get-ChildItem -Recurse -Force -Directory -Path $dst |
            Where-Object { $_.Name -eq "__pycache__" } |
            Remove-Item -Recurse -Force
    }
    else {
        Copy-Item -Force -Path $src -Destination $dst
    }
}

Write-Host "Deployed $PackageName to $Dest"
Write-Host "Restart Sublime Text (or run 'Package Control: Satisfy Dependencies') to load it."
