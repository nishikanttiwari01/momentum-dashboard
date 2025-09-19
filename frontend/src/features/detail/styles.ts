// src/features/detail/styles.ts
import type { SxProps, Theme } from '@mui/material/styles';

export const APP_BAR_HEIGHT = 64;

// Reduced widths (~12–15% narrower)
export const drawerPaperSx: SxProps<Theme> = {
  width: { xs: '70vw', sm: 640, md: 720, lg: 720 },
  maxWidth: 550,
  p: 0,
  top: APP_BAR_HEIGHT,
  height: `calc(100% - ${APP_BAR_HEIGHT}px)`,
  borderLeft: '1px solid',
  borderColor: 'divider',
  bgcolor: 'background.default',
};

export const sectionDividerSx: SxProps<Theme> = {
  borderColor: 'divider',
};
