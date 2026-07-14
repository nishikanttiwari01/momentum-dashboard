import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('FundNavChart visual treatment', () => {
  it('renders a clean Century Ply-style NAV line with transaction references', () => {
    const source = readFileSync(new URL('../../pages/Portfolio.tsx', import.meta.url), 'utf8');
    expect(source).toContain('data-testid="fund-nav-chart"');
    expect(source).toContain('stroke="#2E90FA"');
    expect(source).toContain('stroke="#F5F5F5"');
    expect(source).toContain('vertical={false}');
    expect(source).toContain('Average NAV');
    expect(source).toContain('Latest NAV');
    expect(source).toContain('fill="#00B386"');
    expect(source).not.toContain('<Area ');
    expect(source).not.toContain('navAreaGradient');
  });
});
