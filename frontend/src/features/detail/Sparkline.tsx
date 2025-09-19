import * as React from 'react';
import { Box } from '@mui/material';

type Props = { title?: string };

export default function Sparkline({ title = '30D sparkline (wire later)' }: Props) {
  return (
    <Box
      sx={{
        height: 84,
        bgcolor: 'action.hover',
        borderRadius: 1,
        mb: 2,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 12,
        color: 'text.secondary',
      }}
      title={title}
    >
      Sparkline (30D)
    </Box>
  );
}
