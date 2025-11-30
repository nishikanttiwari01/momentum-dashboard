import * as React from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import InfoIcon from '@mui/icons-material/Info';

type Props = {
  title?: string;
  body?: React.ReactNode;
  placement?: 'bottom' | 'top' | 'left' | 'right';
  iconSize?: number;
};

/**
 * Standardized info tooltip with consistent styling (light blue pill + card).
 */
export function InfoTooltip({ title, body, placement = 'top', iconSize = 16 }: Props) {
  const content = (
    <Box
      sx={{
        p: 1,
        borderRadius: 1,
        bgcolor: '#e6f0ff',
        border: '1px solid rgba(15,60,115,0.25)',
        boxShadow: '0 8px 18px rgba(15,60,115,0.12)',
        maxWidth: 260,
      }}
    >
      {title ? (
        <Typography variant="body2" sx={{ fontWeight: 700, mb: body ? 0.5 : 0, color: '#0b3a67' }}>
          {title}
        </Typography>
      ) : null}
      {body ? (
        <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.4 }}>
          {body}
        </Typography>
      ) : null}
    </Box>
  );

  return (
    <Tooltip
      title={content}
      placement={placement}
      slotProps={{
        popper: {
          sx: {
            zIndex: (theme) => theme.zIndex.modal + 2,
            '& .MuiTooltip-tooltip': { bgcolor: 'transparent', p: 0, maxWidth: 'none' },
          },
          modifiers: [{ name: 'offset', options: { offset: [0, 8] } }],
        },
      }}
      PopperProps={{ disablePortal: false }}
    >
      <InfoIcon
        sx={{
          color: '#1565c0',
          fontSize: iconSize,
          cursor: 'help',
          verticalAlign: 'middle',
        }}
      />
    </Tooltip>
  );
}

export default InfoTooltip;
