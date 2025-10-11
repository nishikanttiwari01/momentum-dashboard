// frontend/src/components/news/SourceCell.tsx
import * as React from "react";
import type { NewsCard } from "../../lib/api/types/newsCard";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";

type SourceItem = Partial<NewsCard>;

export default function SourceCell({ item }: { item?: SourceItem }) {
  if (!item) {
    return null;
  }
  const sources = Array.isArray(item.sources) ? item.sources : [];
  const fallback = sources.length ? sources[0] : undefined;
  const text = item.source_primary || fallback?.publisher || "-";
  const href = item.source_url || fallback?.url || "";

  if (!href) {
    return <Typography variant="body2" color="text.secondary">{text}</Typography>;
  }
  return (
    <Link href={href} target="_blank" rel="noopener noreferrer" underline="hover">
      {text}
    </Link>
  );
}
