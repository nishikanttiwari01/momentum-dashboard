$ErrorActionPreference = "Stop"

$htmlPath = Join-Path $PSScriptRoot "portfolio-workbook-dashboard.html"
if (-not (Test-Path -LiteralPath $htmlPath)) {
    throw "Mockup HTML is missing: $htmlPath"
}

$html = Get-Content -LiteralPath $htmlPath -Raw -Encoding UTF8

$required = @(
    'data-testid="portfolio-overview"',
    'data-testid="asset-allocation-chart"',
    'data-testid="fund-allocation-chart"',
    'data-testid="portfolio-history-chart"',
    'data-panel="mutual-funds"',
    'data-panel="equity"',
    'data-panel="fixed-assets"',
    'data-panel="upload-preview"',
    'accept=".xlsx"',
    'BALANCE SHEET',
    'CURRENT ASSET',
    'FUNDS',
    'Funds XIRR',
    'Final XIRR',
    'EQUITY',
    'FIXED ASSET'
)

foreach ($needle in $required) {
    if (-not $html.Contains($needle)) {
        throw "Required mockup contract is missing: $needle"
    }
}

$forbiddenPatterns = @(
    'type\s*=\s*["'']password',
    '>\s*LOGIN\s*<',
    '>\s*PASSWORD\s*<',
    '>\s*FOLIO(?: NO)?\s*<',
    '>\s*ACCOUNT(?: NO| NUMBER)?\s*<'
)

foreach ($pattern in $forbiddenPatterns) {
    if ($html -match $pattern) {
        throw "Sensitive UI field detected: $pattern"
    }
}

$principal = 58663055.25
$marketValue = 83058852.25
$expectedGain = [math]::Round($marketValue - $principal, 2)
if ($html -notmatch ('data-total-gain="' + [regex]::Escape($expectedGain.ToString('0.00', [Globalization.CultureInfo]::InvariantCulture)) + '"')) {
    throw "Overview gain does not reconcile with the workbook balance-sheet totals"
}

Write-Output "PASS: portfolio workbook dashboard mockup contract"
