// src/theme/index.ts
import { createTheme } from '@mui/material/styles';
import { buildPalette } from './presets';
import { componentOverrides } from './overrides';

export type ThemePreset = 'default'|'secondary'|'success'|'dark';

export const createAppTheme = (preset: ThemePreset = 'default') => {
  const palette = buildPalette(preset);

  const theme = createTheme({
    palette,
    shape:{ borderRadius:14 },
    typography:{
      fontFamily: ['Inter','Segoe UI','Roboto','Helvetica Neue','Arial','Noto Sans','sans-serif'].join(','),
      h1:{ fontSize:'3rem', fontWeight:800, letterSpacing:.2 },
      h2:{ fontSize:'2rem', fontWeight:800, letterSpacing:.2 },
      h3:{ fontSize:'1.6rem', fontWeight:800, letterSpacing:.2 },
      h4:{ fontSize:'1.3rem', fontWeight:800 },
      h5:{ fontSize:'1.1rem', fontWeight:800 },
      h6:{ fontSize:'1.0rem', fontWeight:800 },
      subtitle1:{ fontWeight:700 },
      button:{ textTransform:'none', fontWeight:700 },
    },
    shadows: [
      'none',
      '0 1px 2px rgba(0,0,0,.06),0 4px 10px rgba(0,0,0,.05)',
      '0 1px 2px rgba(0,0,0,.08),0 6px 14px rgba(0,0,0,.06)',
      '0 2px 12px rgba(0,0,0,.08)',
      ...Array(21).fill('0 2px 12px rgba(0,0,0,.08)'),
    ] as any,
  });

  // attach component overrides
  theme.components = componentOverrides(theme);
  return theme;
};
