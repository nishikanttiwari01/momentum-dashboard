import { defineConfig } from 'orval';

export default defineConfig({
  momentum: {
    input: '../contracts/openapi.yaml',
    output: {
      client: 'react-query',
      target: './src/lib/api/client.ts',   // single file with hooks
      schemas: './src/lib/api/types',   // single file with types
      mode: 'single',
      clean: true,                         // <— clean old output before generate
      prettier: true
    },
    hooks: true
  }
});
