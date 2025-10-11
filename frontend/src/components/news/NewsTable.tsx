// frontend/src/components/news/NewsTable.tsx
import * as React from "react";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import RefreshIcon from "@mui/icons-material/Refresh";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(utc);
dayjs.extend(timezone);

import { useAllNewsInfinite } from "../../lib/hooks";
import type {
  ListAllNewsParams,
  NewsCard,
} from "../../lib/api/types";

import SourceCell from "./SourceCell";
import SentimentChip from "./SentimentChip";
import EventChip from "./EventChip";
import BulletsCell from "./BulletsCell";

export type NewsTableProps = {
  params?: ListAllNewsParams;
  height?: number | string;
  title?: string;
};

export default function NewsTable({
  params,
  height = 640,
  title = "News",
}: NewsTableProps) {
  const memoParams = React.useMemo<Omit<ListAllNewsParams, "page" | "per_page"> | undefined>(() => {
    if (!params) return undefined;
    const { page: _page, per_page: _perPage, ...rest } = params;
    return { ...rest };
  }, [params]);

  const perPage = 500;
  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetching,
    isFetchingNextPage,
    refetch,
  } = useAllNewsInfinite(
    memoParams ? { ...memoParams } : undefined,
    { perPage, staleTimeMs: 60_000, enabled: memoParams !== undefined }
  );

  React.useEffect(() => {
    if (!memoParams) return;
    if (hasNextPage && !isFetchingNextPage && !isLoading) {
      void fetchNextPage();
    }
  }, [memoParams, hasNextPage, isFetchingNextPage, isLoading, fetchNextPage]);

  const items = React.useMemo(() => {
    const out: NewsCard[] = [];
    const seen = new Set<string>();
    data?.pages?.forEach((page) => {
      (page.items ?? []).forEach((it) => {
        if (!seen.has(it.cluster_id)) {
          seen.add(it.cluster_id);
          out.push(it);
        }
      });
    });
    return out;
  }, [data]);

  const handleRefresh = () => {
    refetch();
  };

  const rows = React.useMemo(
    () =>
      items.map((it: NewsCard, idx: number) => ({
        id: it.cluster_id || `${idx}`,
        ...it,
        symbol: it.symbol ?? "",
        sources: it.sources ?? [],
        published: it.published ?? null,
      })),
    [items]
  );

  const cols = React.useMemo<GridColDef[]>(
    () => [
      {
        field: "published",
        headerName: "Time",
        width: 160,
        valueFormatter: (params) => {
          const value = params.value as string | null | undefined;
          if (!value) return "";
          const tz = dayjs.tz?.guess?.() ?? "UTC";
          return dayjs(value).tz(tz).format("YYYY-MM-DD HH:mm");
        },
      },
      { field: "symbol", headerName: "Symbol", width: 120 },
      { field: "title", headerName: "Title", flex: 1, minWidth: 260 },
      {
        field: "event_type",
        headerName: "Event",
        width: 130,
        renderCell: (p: GridRenderCellParams<string>) => (
          <EventChip value={p.value} />
        ),
        sortable: false,
      },
      {
        field: "bullets",
        headerName: "Summary",
        flex: 1.4,
        minWidth: 300,
        sortable: false,
        renderCell: (p: GridRenderCellParams<string[]>) => (
          <BulletsCell
            bullets={p.value || []}
            why={(p.row as any)?.why}
          />
        ),
      },
      {
        field: "source",
        headerName: "Source",
        width: 180,
        sortable: false,
        renderCell: (p) => {
          const row = p.row as Partial<NewsCard> | undefined;
          return <SourceCell item={row} />;
        },
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

  const windowLabel = React.useMemo(() => {
    const firstPage = data?.pages?.[0];
    const win = firstPage?.window;
    if (!win) return null;
    const { from, to } = win;
    const tz = dayjs.tz.guess();
    const start = dayjs(from).tz(tz);
    const end = dayjs(to).tz(tz);
    const sameDay = start.format("YYYY-MM-DD") === end.format("YYYY-MM-DD");
    const startLabel = start.format("YYYY-MM-DD HH:mm");
    const endLabel = end.format(sameDay ? "HH:mm" : "YYYY-MM-DD HH:mm");
    return `${startLabel} \u2013 ${endLabel}`;
  }, [data?.pages]);

  return (
    <Paper elevation={1} sx={{ p: 2 }}>
      <Box
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 1 }}
      >
        <Box>
          <Typography variant="h6">{title}</Typography>
          {windowLabel ? (
            <Typography variant="caption" color="text.secondary">
              Window: {windowLabel}
            </Typography>
          ) : null}
        </Box>
        <IconButton onClick={handleRefresh} size="small" aria-label="Refresh">
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Box>
      <div style={{ height, width: "100%" }}>
        <DataGrid
          density="compact"
          rows={rows}
          columns={cols}
          loading={isLoading && !data}
          disableRowSelectionOnClick
          autoHeight={typeof height === "string"}
          getRowHeight={() => "auto"}
          sx={{
            "& .MuiDataGrid-cell": { alignItems: "flex-start" },
            "& .MuiDataGrid-cellContent": {
              whiteSpace: "normal",
              lineHeight: 1.35,
            },
          }}
        />
      </div>
      {hasNextPage ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 1 }}>
          <Button
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            size="small"
            variant="outlined"
          >
            {isFetchingNextPage ? "Loading..." : "Load more"}
          </Button>
        </Box>
      ) : null}
      {isError ? (
        <Typography variant="body2" color="error" sx={{ mt: 1 }}>
          Failed to load news. Check API connectivity.
        </Typography>
      ) : null}
    </Paper>
  );
}
