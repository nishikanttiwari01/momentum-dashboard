// src/theme/presets.ts
import tinycolor from 'tinycolor2';

type Hex = string;
const lighten = (c:Hex, r=7.5)=> tinycolor(c).lighten(r).toHexString();
const darken  = (c:Hex, r=15)=> tinycolor(c).darken(r).toHexString();

export const presets = {
  default: {
    mode: 'light' as const,
    primary:  '#536DFE',
    secondary:'#FF5C93',
    warning:  '#FFC260',
    success:  '#3CD4A0',
    info:     '#9013FE',
  },
  secondary: {
    mode: 'light' as const,
    primary:  '#EE266D',
    secondary:'#536DFE',
    warning:  '#FFC260',
    success:  '#63C5B5',
    info:     '#AE1ECC',
  },
  success: {
    mode: 'light' as const,
    primary:  '#3CD4A0',
    secondary:'#536DFE',
    warning:  '#FFC260',
    success:  '#22c55e',
    info:     '#9013FE',
  },
  dark: {
    mode: 'dark' as const,
    primary:  '#536DFE',
    secondary:'#EE266D',
    warning:  '#E9B55F',
    success:  '#63C5B5',
    info:     '#AE1ECC',
  },
} as const;

export const buildPalette = (preset: keyof typeof presets) => {
  const p = presets[preset];
  return {
    mode: p.mode,
    primary:  { main: p.primary,  light: lighten(p.primary),  dark: darken(p.primary) },
    secondary:{ main: p.secondary,light: lighten(p.secondary),dark: darken(p.secondary), contrastText:'#fff' },
    warning:  { main: p.warning,  light: lighten(p.warning),  dark: darken(p.warning) },
    success:  { main: p.success,  light: lighten(p.success),  dark: darken(p.success) },
    info:     { main: p.info,     light: lighten(p.info),     dark: darken(p.info) },
    background: p.mode==='dark'
      ? { default:'#0f1117', paper:'#0f141f' }
      : { default:'#f5f7fb', paper:'#ffffff' },
    divider:  p.mode==='dark' ? '#202636' : '#e6e8ef',
    text:     p.mode==='dark'
      ? { primary:'#e5e7eb', secondary:'#9ca3af' }
      : { primary:'#1f2937', secondary:'#6b7280' },
  };
};
