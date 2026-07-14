import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('FundNavChart visual treatment', () => {
  it('renders a gradient NAV area with average and latest-value emphasis', () => {
    const source = readFileSync(new URL('../../pages/Portfolio.tsx', import.meta.url), 'utf8');
    expect(source).toContain('Area');
    expect(source).toContain('navAreaGradient');
    expect(source).toContain('data-testid="fund-nav-chart"');
    expect(source).toContain('Average NAV');
    expect(source).toContain('Latest NAV');
    expect(source).toContain('filter: \'drop-shadow');
    expect(source).toContain('dx: -58');
  });
});
