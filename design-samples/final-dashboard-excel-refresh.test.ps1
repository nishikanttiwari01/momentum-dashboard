$ErrorActionPreference = "Stop"
$path = Join-Path $PSScriptRoot "final-dashboard-excel-refresh.html"
if (-not (Test-Path -LiteralPath $path)) { throw "Updated design sample is missing: $path" }
$html = Get-Content -LiteralPath $path -Raw -Encoding UTF8
$required = @(
  'id="excel-refresh"',
  'id="excel-file"',
  'accept=".xlsx"',
  'id="import-preview"',
  'BALANCE SHEET',
  'CURRENT ASSET',
  'Funds XIRR',
  'Final XIRR',
  'FIXED ASSET',
  'function previewWorkbook'
)
foreach ($value in $required) {
  if (-not $html.Contains($value)) { throw "Missing Excel refresh contract: $value" }
}
if ($html -match 'type\s*=\s*["'']password') { throw "Sensitive input field detected" }
Write-Output "PASS: final dashboard Excel refresh sample contract"
