$ErrorActionPreference = "Stop"
$manifest = "docs/Claudedocs/SeedSetup/manifests_seed_papers.csv"
$dest = "assets/papers"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Import-Csv $manifest | ForEach-Object {
  if ([string]::IsNullOrWhiteSpace($_.pdf_url)) {
    Write-Host "SKIP: $($_.slug) (no direct PDF; use Unpaywall or save page as PDF)"
  } else {
    $out = Join-Path $dest ($_.slug + ".pdf")
    if (Test-Path $out) {
      Write-Host "EXISTS: $($_.slug)" -ForegroundColor Yellow
    } else {
      Write-Host "DOWNLOADING: $($_.slug)"
      Invoke-WebRequest -Uri $_.pdf_url -OutFile $out
    }
  }
}
Write-Host "Done."
