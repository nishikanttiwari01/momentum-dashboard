import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { commitWorkbook, previewWorkbook } from './wealthApi';

vi.mock('axios');
const mockedAxios = vi.mocked(axios, true);

describe('wealthApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uploads the workbook using multipart FormData', async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: { preview_token: 'p1' } });
    const file = new File(['xlsx'], 'investment.xlsx');
    await previewWorkbook(file);
    const [url, body] = mockedAxios.post.mock.calls[0];
    expect(url).toBe('/api/v1/wealth-portfolio/imports/preview');
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('workbook')).toBe(file);
  });

  it('commits the selected preview token', async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: { snapshot_id: 's1', created: true } });
    await commitWorkbook('p1');
    expect(mockedAxios.post).toHaveBeenCalledWith('/api/v1/wealth-portfolio/imports/p1/commit');
  });
});
