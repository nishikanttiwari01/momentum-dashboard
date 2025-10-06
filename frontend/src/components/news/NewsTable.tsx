// frontend/src/components/news/NewsTable.tsx
import * as React from "react";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import RefreshIcon from "@mui/icons-material/Refresh";
import dayjs from "dayjs";

// ⬇️ use your generated wrapper + types
import { useNewsList } from "../../lib/hooks";
import type { GetNewsListParams } from "../../lib/api/types/getNewsListParams";
import type { NewsCard } from "../../lib/api/types/newsCard";

import SourceCell from "./SourceCell";
import SentimentChip from "./SentimentChip";
import EventChip from "./EventChip";
import BulletsCell from "./BulletsCell";

export type NewsTableProps = GetNewsListParams & {
  height?: number | string;
  title?: string;
};

export default function NewsTable(props: NewsTableProps) {
  const {
    symbol = "",
    from = new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
    to = new Date().toISOString(),
    page = 1,
    per_page = 50,
    min_confidence,
    event,
    sort = "impact_desc",
    height = 640,
    title = "News",
  } = props;

  // ⬇️ call your generated hook
  const { data, isLoading, isError, refetch } = useNewsList(
    { symbol, from, to, page, per_page, min_confidence, event, sort },
    undefined
  );

  const rows = React.useMemo(
    () =>
      (data?.items ?? []).map((it: NewsCard, idx: number) => ({
        id: it.cluster_id || `${idx}`,
        ...it,
      })),
    [data]
  );

  const cols = React.useMemo<GridColDef[]>(
    () => [
      {
        field: "published",
        headerName: "Time",
        width: 160,
        valueGetter: (params) =>
          dayjs(params.value as string).local().format("YYYY-MM-DD HH:mm"),
      },
      { field: "symbol", headerName: "Symbol", width: 120 },
      { field: "title", headerName: "Title", flex: 1, minWidth: 260 },
      {
        field: "event_type",
        headerName: "Event",
        width: 130,
        renderCell: (p: GridRenderCellParams<string>) => <EventChip value={p.value} />,
        sortable: false,
      },
      {
        field: "bullets",
        headerName: "Summary",
        flex: 1.4,
        minWidth: 300,
        sortable: false,
        renderCell: (p: GridRenderCellParams<string[]>) => (
          <BulletsCell bullets={p.value || []} why={(p.api.getRow(p.id) as any)?.why} />
        ),
      },
      {
        field: "source",
        headerName: "Source",
        width: 180,
        sortable: false,
        valueGetter: (p) =>
          p.row.source_primary || p.row.sources?.[0]?.publisher || "",
        renderCell: (p) => <SourceCell item={p.api.getRow(p.id) as NewsCard} />,
      },
      {
        field: "sentiment",
        headerName: "Sentiment",
        width: 130,
        sortable: false,
        renderCell: (p: GridRenderCellParams<string>) => (
          <SentimentChip value={p.value} />
        ),
      },
      { field: "confidence_stars", headerName: "Conf", width: 80 },
      {
        field: "consensus_score",
        headerName: "Score",
        width: 90,
        valueFormatter: (p) =>
          p.value == null ? "" : Number(p.value).toFixed(2),
      },
    ],
    []
  );

  return (
    <Paper elevation={1} sx={{ p: 2 }}>
      <Box display="flex" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="h6">{title}</Typography>
        <IconButton onClick={() => refetch()} size="small" aria-label="Refresh">
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Box>
      <div style={{ height, width: "100%" }}>
        <DataGrid
          density="compact"
          rows={rows}
          columns={cols}
          loading={isLoading}
          disableRowSelectionOnClick
          autoHeight={typeof height === "string"}
          getRowHeight={() => "auto"}
          sx={{
            "& .MuiDataGrid-cell": { alignItems: "flex-start" },
            "& .MuiDataGrid-cellContent": { whiteSpace: "normal", lineHeight: 1.35 },
          }}
        />
      </div>
      {isError ? (
        <Typography variant="body2" color="error" sx={{ mt: 1 }}>
          Failed to load news. Check API connectivity.
        </Typography>
      ) : null}
    </Paper>
  );
}
