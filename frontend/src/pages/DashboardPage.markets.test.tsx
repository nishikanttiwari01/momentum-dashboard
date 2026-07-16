import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(fileURLToPath(new URL('./DashboardPage.tsx', import.meta.url)), 'utf8');
const marketsLabel = '<SectionBand color="#7C3AED" label="Markets — India & US" />';
const investmentsLabel = '<SectionBand color="#00B386" label="My investments — open trades" />';

function expectMarketsPlacement(pageSource: string) {
  const dataHealthPanel = pageSource.indexOf('<DataHealthPanel />');
  const marketsBand = pageSource.indexOf(marketsLabel);
  const investmentsBand = pageSource.indexOf(investmentsLabel);

  expect(dataHealthPanel).toBeGreaterThan(-1);
  expect(marketsBand).toBeGreaterThan(dataHealthPanel);
  expect(investmentsBand).toBeGreaterThan(marketsBand);
  expect(pageSource).toMatch(
    /<Box sx=\{\{ px: \{ xs: 1, md: 2 \}, pt: 1 \}\}>\s*<DataHealthPanel \/>\s*<\/Box>\s*<SectionBand color="#7C3AED" label="Markets — India & US" \/>/,
  );
}

describe('DashboardPage markets composition', () => {
  it('places both responsive market index cards before open investments', () => {
    expect(source).toContain("import MarketIndexChartCard from '../components/MarketIndexChartCard';");

    expectMarketsPlacement(source);

    const marketsBand = source.indexOf(marketsLabel);
    const investmentsBand = source.indexOf(investmentsLabel);
    const marketsSection = source.slice(marketsBand, investmentsBand);
    expect(marketsSection).toMatch(
      /<Grid container[^>]*>[\s\S]*?<Grid item xs=\{12\} lg=\{6\}>\s*<MarketIndexChartCard marketKey="sensex" \/>\s*<\/Grid>[\s\S]*?<Grid item xs=\{12\} lg=\{6\}>\s*<MarketIndexChartCard marketKey="sp500" \/>\s*<\/Grid>[\s\S]*?<\/Grid>/,
    );
  });

  it('rejects moving the markets section above data health', () => {
    const marketsStart = source.indexOf(marketsLabel);
    const investmentsStart = source.indexOf(investmentsLabel);
    const marketsSection = source.slice(marketsStart, investmentsStart);
    const withoutMarkets = source.slice(0, marketsStart) + source.slice(investmentsStart);
    const dataHealthBox = withoutMarkets.indexOf('<Box sx={{ px: { xs: 1, md: 2 }, pt: 1 }}>');
    const misplacedSource = withoutMarkets.slice(0, dataHealthBox) + marketsSection + withoutMarkets.slice(dataHealthBox);

    expect(() => expectMarketsPlacement(misplacedSource)).toThrow();
  });
});
