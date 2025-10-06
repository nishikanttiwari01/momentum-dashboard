// frontend/src/components/news/BulletsCell.tsx
import * as React from "react";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";

export default function BulletsCell({ bullets, why }: { bullets: string[]; why?: string }) {
  const list = (bullets || []).slice(0, 4).map((b) => b.replace(/^•\s?/, ""));
  return (
    <Box>
      {list.length ? (
        <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
          {list.map((b, i) => (
            <li key={i}>
              <Typography variant="body2">{b}</Typography>
            </li>
          ))}
        </ul>
      ) : (
        <Typography variant="body2" color="text.secondary">
          No summary
        </Typography>
      )}
      {why ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
          {why}
        </Typography>
      ) : null}
    </Box>
  );
}
