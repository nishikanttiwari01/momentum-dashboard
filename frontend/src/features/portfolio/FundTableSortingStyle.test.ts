import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('mutual-fund table sorting integration', () => {
  it('uses accessible sort labels for data columns and sorted rows', () => {
    const source = readFileSync(new URL('../../pages/Portfolio.tsx', import.meta.url), 'utf8');
    expect(source).toContain('TableSortLabel');
    expect(source).toContain("import { sortFunds");
    expect(source).toContain('SORTABLE_FUND_COLUMNS');
    expect(source).toContain("label: 'Fund'");
    expect(source).toContain("label: 'XIRR'");
    expect(source).toContain('const sortedFunds = React.useMemo');
    expect(source).toContain('sortedFunds.map((f) =>');
    expect(source).toContain('<TableCell align="center">Action</TableCell>');
    expect(source).toContain('<TableCell align="center">Links</TableCell>');
    expect(source).toContain('hideSortIcon={false}');
    expect(source).toContain("'& .MuiTableSortLabel-icon': { opacity: 0.35 }");
    expect(source).toContain("'&.Mui-active .MuiTableSortLabel-icon': { opacity: 1, color: 'primary.main' }");
  });
});
