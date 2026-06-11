param(
    [switch]$Clean,
    [switch]$Crawl,
    [switch]$DiscoverOnly,
    [int]$MaxArticles = 0,
    [int]$Workers = 6,
    [int]$MinImages = 1
)

# Extract visual step guides from support.microsoft.com into kb_visual_assets/
# Full crawl:  .\scripts\support_extractor\run_extract.ps1 -Crawl -Clean
# Quick test:  .\scripts\support_extractor\run_extract.ps1 -Crawl -Clean -MaxArticles 30

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$Script = Join-Path $PSScriptRoot "extract_support_guides.py"

$ArgsList = @()
if ($Clean) { $ArgsList += "--clean" }
if ($Crawl) { $ArgsList += "--crawl" }
if ($DiscoverOnly) { $ArgsList += "--discover-only" }
if ($MaxArticles -gt 0) { $ArgsList += "--max-articles"; $ArgsList += "$MaxArticles" }
$ArgsList += "--workers"; $ArgsList += "$Workers"
$ArgsList += "--min-images"; $ArgsList += "$MinImages"

& $Python $Script @ArgsList @args
