// frontend/src/components/news/NewsPanel.tsx
import * as React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import CircularProgress from "@mui/material/CircularProgress";
import { useNewsList } from "../../lib/hooks";
import type { NewsCard } from "../../lib/api/types/newsCard";

export default function NewsPanel({
  symbol,
  hours = 24,
}: {
  symbol: string;
  hours?: number;
}) {
  const toISO = new Date().toISOString();
  const fromISO = new Date(Date.now() - hours * 3600 * 1000).toISOString();

  const { data, isLoading, isError } = useNewsList({
    symbol,
    from: fromISO,
    to: toISO,
    page: 1,
    per_page: 50,
    sort: "impact_desc",
  });

  const items = (data?.items ?? []) as NewsCard[];

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
        <CircularProgress size={22} />
      </Box>
    );
  }
  if (isError) {
    return (
      <Typography variant="body2" color="error">
        Failed to load news.
      </Typography>
    );
  }
  if (!items.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No news in the last {hours}h.
      </Typography>
    );
  }

  return (
    <List disablePadding>
      {items.map((it, idx) => {
        const primary = it.title;
        const srcText = it.source_primary || it.sources?.[0]?.publisher || "";
        const href = it.source_url || it.sources?.[0]?.url || "";
        const bullets = (it.bullets || []).slice(0, 3).map(b => b.replace(/^•\s?/, ""));

        return (
          <React.Fragment key={it.cluster_id || `${idx}`}>
            <ListItem alignItems="flex-start" disableGutters sx={{ py: 1.25 }}>
              <ListItemText
                primary={
                  <Typography variant="subtitle2" sx={{ lineHeight: 1.3 }}>
                    {primary}
                  </Typography>
                }
                secondary={
                  <Box sx={{ mt: 0.5 }}>
                    {bullets.length ? (
                      <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                        {bullets.map((b, i) => (
                          <li key={i}>
                            <Typography variant="body2">{b}</Typography>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {it.why ? (
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                        {it.why}
                      </Typography>
                    ) : null}
                    {href ? (
                      <Typography variant="caption" display="block" sx={{ mt: 0.75 }}>
                        Source:{" "}
                        <Link href={href} target="_blank" rel="noopener noreferrer" underline="hover">
                          {srcText || "link"}
                        </Link>
                      </Typography>
                    ) : srcText ? (
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                        Source: {srcText}
                      </Typography>
                    ) : null}
                  </Box>
                }
              />
            </ListItem>
            {idx < items.length - 1 ? <Divider component="li" /> : null}
          </React.Fragment>
        );
      })}
    </List>
  );
}
