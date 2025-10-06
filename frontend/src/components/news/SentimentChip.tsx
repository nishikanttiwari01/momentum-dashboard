// frontend/src/components/news/SentimentChip.tsx
import * as React from "react";
import Chip from "@mui/material/Chip";

function colorFor(sent?: string): "default" | "success" | "error" | "warning" {
  const s = (sent || "").toLowerCase();
  if (s === "positive") return "success";
  if (s === "negative") return "error";
  if (s === "mixed") return "warning";
  return "default";
}

export default function SentimentChip({ value }: { value?: string }) {
  return <Chip size="small" label={value || "neutral"} color={colorFor(value)} variant="outlined" />;
}
