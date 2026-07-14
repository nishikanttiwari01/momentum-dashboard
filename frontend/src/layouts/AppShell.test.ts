import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

describe('AppShell responsive sizing', () => {
  it('allows the main flex item to shrink within the viewport', () => {
    const source = fs.readFileSync(path.resolve(__dirname, 'AppShell.tsx'), 'utf8');

    expect(source).toMatch(/component="main"[\s\S]*?minWidth:\s*0/);
  });
});
