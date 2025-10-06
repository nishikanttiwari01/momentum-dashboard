// frontend/src/components/shell/RightNewsDrawerTabs.tsx
import * as React from "react";
import Drawer from "@mui/material/Drawer";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import RefreshIcon from "@mui/icons-material/Refresh";

import NewsPanel from "../news/NewsPanel";

export type RightNewsDrawerTabsProps = {
  open: boolean;
  onClose: () => void;
  symbol: string;   // e.g., "RELIANCE.NS"
  hours?: number;   // default 24
  width?: number;   // default 420
};

export default function RightNewsDrawerTabs({
  open,
  onClose,
  symbol,
  hours = 24,
  width = 420,
}: RightNewsDrawerTabsProps) {
  const [tab, setTab] = React.useState(0);
  const handleTab = (_e: any, v: number) => setTab(v);

  // simple tab header refresh pattern – NewsPanel itself re-fetches via react-query on params change.
  const refreshRef = React.useRef<() => void>();
  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width } }}>
      <Box sx={{ px: 2, pt: 2, pb: 1, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="h6">Right Panel</Typography>
        <IconButton
          size="small"
          aria-label="Refresh"
          onClick={() => refreshRef.current?.()}
          title="Refresh"
        >
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Box>

      <Tabs value={tab} onChange={handleTab} variant="fullWidth">
        <Tab label="News" />
        {/* Add more <Tab /> items later if needed */}
      </Tabs>

      <Box sx={{ p: 2, pt: 1, height: "100%", overflowY: "auto" }}>
        {tab === 0 ? (
          <NewsPanel symbol={symbol} hours={hours} />
        ) : null}
      </Box>
    </Drawer>
  );
}
