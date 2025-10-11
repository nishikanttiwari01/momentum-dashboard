import * as React from "react";
import dayjs from "dayjs";
import {
  Box,
  Button,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import NewsTable from "@/components/news/NewsTable";
import type { ListAllNewsParams } from "@/lib/api/types";

export default function News() {
  const today = React.useMemo(() => dayjs().format("YYYY-MM-DD"), []);
  const [selectedDate, setSelectedDate] = React.useState<string>(today);

  const handleShift = React.useCallback(
    (delta: number) => {
      setSelectedDate((prev) =>
        dayjs(prev || today).add(delta, "day").format("YYYY-MM-DD")
      );
    },
    [today]
  );

  const handleDateChange = React.useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const value = event.target.value;
      setSelectedDate(value ? dayjs(value).format("YYYY-MM-DD") : today);
    },
    [today]
  );

  const queryParams = React.useMemo<ListAllNewsParams>(
    () => ({
      on: selectedDate,
      align: "calendar_day",
      sort: "impact_desc",
    }),
    [selectedDate]
  );

  const isToday = selectedDate === today;

  return (
    <Paper
      sx={{
        p: 2,
        width: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 1,
      }}
    >
      <Stack
        direction={{ xs: "column", sm: "row" }}
        alignItems={{ xs: "flex-start", sm: "center" }}
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 1 }}
      >
        <Stack spacing={0.25}>
          <Typography variant="subtitle2">All News Feed</Typography>
          <Typography variant="caption" color="text.secondary">
            Aggregated news clusters for the selected trading day (IST)
          </Typography>
        </Stack>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          alignItems={{ xs: "stretch", sm: "center" }}
        >
          <Button
            variant="outlined"
            size="small"
            onClick={() => handleShift(-1)}
          >
            Previous
          </Button>
          <TextField
            size="small"
            label="Trading Day"
            type="date"
            value={selectedDate}
            onChange={handleDateChange}
            InputLabelProps={{ shrink: true }}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={isToday}
            onClick={() => handleShift(1)}
          >
            Next
          </Button>
          <Button
            variant="contained"
            size="small"
            disabled={isToday}
            onClick={() => setSelectedDate(today)}
          >
            Today
          </Button>
        </Stack>
      </Stack>
      <Divider sx={{ mb: 1 }} />

      <Box sx={{ width: "100%" }}>
        <NewsTable
          params={queryParams}
          height="auto"
          title={`News (${selectedDate})`}
        />
      </Box>
    </Paper>
  );
}
