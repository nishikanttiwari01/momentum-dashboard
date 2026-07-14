import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('Portfolio page visual structure', () => {
  it('uses shared metric tiles and stable styled section hooks', () => {
    const source = readFileSync(new URL('./Portfolio.tsx', import.meta.url), 'utf8');
    const usSource = readFileSync(new URL('../features/portfolio/UsInvestmentsSection.tsx', import.meta.url), 'utf8');
    expect(source).toContain('PortfolioMetricTile');
    expect(source).toContain('data-testid="portfolio-signals"');
    expect(source).toContain('data-testid="portfolio-funds"');
    expect(source).toContain('PortfolioSectionHeader');
    expect(usSource).toContain('data-testid="portfolio-qqq"');
    expect(usSource).toContain('PortfolioSectionHeader');
  });
});
