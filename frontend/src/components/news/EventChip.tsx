// frontend/src/components/news/EventChip.tsx
import * as React from "react";
import Chip from "@mui/material/Chip";

export default function EventChip({ value }: { value?: string }) {
  return <Chip size="small" label={value || "other"} variant="outlined" />;
}
