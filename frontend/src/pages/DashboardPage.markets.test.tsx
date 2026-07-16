import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(fileURLToPath(new URL('./DashboardPage.tsx', import.meta.url)), 'utf8');

describe('DashboardPage markets composition', () => {
  it('places both responsive market index cards before open investments', () => {
    expect(source).toContain("import MarketIndexChartCard from '../components/MarketIndexChartCard';");

    const marketsBand = source.indexOf('<SectionBand color="#7C3AED" label="Markets — India & US" />');
    const investmentsBand = source.indexOf('<SectionBand color="#00B386" label="My investments — open trades" />');

    expect(marketsBand).toBeGreaterThan(-1);
    expect(investmentsBand).toBeGreaterThan(marketsBand);

    const marketsSection = source.slice(marketsBand, investmentsBand);
    expect(marketsSection).toMatch(
      /<Grid container[^>]*>[\s\S]*?<Grid item xs=\{12\} lg=\{6\}>\s*<MarketIndexChartCard marketKey="sensex" \/>\s*<\/Grid>[\s\S]*?<Grid item xs=\{12\} lg=\{6\}>\s*<MarketIndexChartCard marketKey="sp500" \/>\s*<\/Grid>[\s\S]*?<\/Grid>/,
    );
  });
});
