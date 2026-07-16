import React from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { formatCrore } from "./familyWealthMath";
import type { FamilyPlanDraft } from "./FamilyPlanAssumptions";
import type { FamilyPlanResponse, FamilyPlanUpdate } from "./wealthTypes";

type Props = {
  data: FamilyPlanResponse;
  draft: FamilyPlanDraft;
  onChange: (d: FamilyPlanDraft) => void;
  onSave: (p: FamilyPlanUpdate) => void;
  toUpdate: (d: FamilyPlanDraft) => FamilyPlanUpdate;
  dirty: boolean;
  disabled: boolean;
  fieldErrors: Partial<Record<string, string>>;
};
const labels = {
  conservative: "Conservative",
  expected: "Expected",
  optimistic: "Optimistic",
} as const;
export const FamilyScenarioMatrix: React.FC<Props> = ({
  data,
  draft,
  onChange,
  onSave,
  toUpdate,
  dirty,
  disabled,
  fieldErrors,
}) => {
  const change = (i: number, key: string, value: string | boolean) =>
    onChange({
      ...draft,
      scenarios: draft.scenarios.map((s, n) =>
        n === i ? { ...s, [key]: value } : s,
      ),
    });
  const field = (
    i: number,
    key: keyof FamilyPlanDraft["scenarios"][number],
    label: string,
  ) => (
    <TextField
      size="small"
      label={label}
      type="number"
      value={String(draft.scenarios[i][key])}
      disabled={
        disabled ||
        (key === "step_up_pct" && !draft.scenarios[i].step_up_enabled)
      }
      onChange={(e) => change(i, key, e.target.value)}
      error={!!fieldErrors[`scenarios.${i}.${key}`]}
      helperText={fieldErrors[`scenarios.${i}.${key}`]}
      inputProps={{ step: 0.1 }}
    />
  );
  return (
    <Box component="section" aria-labelledby="scenario-matrix-title">
      <Typography id="scenario-matrix-title" variant="h5" fontWeight={900}>
        Scenario comparison
      </Typography>
      <Typography color="text.secondary" mb={1}>
        Tune financial and property assumptions independently. Results remain
        last saved until recalculated.
      </Typography>
      {dirty && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          Draft values are not yet reflected in the calculated results.
        </Alert>
      )}
      <Box
        sx={{ overflowX: "auto", maxWidth: "100%" }}
        data-testid="scenario-matrix-scroll"
      >
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "160px repeat(3,minmax(220px,1fr))",
            minWidth: 820,
            gap: 1,
          }}
        >
          <Box />
          <>
            {draft.scenarios.map((s) => (
              <Typography key={s.scenario_key} fontWeight={900}>
                {labels[s.scenario_key]}
              </Typography>
            ))}
          </>
          {(
            [
              "Financial return (%)",
              "Property growth (%)",
              "Monthly investment",
              "Annual step-up",
              "Step-up (%)",
              "Contribution stop age",
            ] as const
          ).map((label, row) => (
            <React.Fragment key={label}>
              <Typography alignSelf="center" fontWeight={700}>
                {label}
              </Typography>
              {draft.scenarios.map((s, i) =>
                row === 3 ? (
                  <FormControlLabel
                    key={s.scenario_key}
                    control={
                      <Checkbox
                        checked={s.step_up_enabled}
                        onChange={(e) =>
                          change(i, "step_up_enabled", e.target.checked)
                        }
                      />
                    }
                    label={s.step_up_enabled ? "On" : "Off"}
                  />
                ) : (
                  field(
                    i,
                    (
                      [
                        "financial_return_pct",
                        "property_growth_pct",
                        "monthly_contribution_inr",
                        "step_up_enabled",
                        "step_up_pct",
                        "contribution_stop_age",
                      ] as const
                    )[row],
                    label,
                  )
                ),
              )}
            </React.Fragment>
          ))}
          <Typography fontWeight={700}>
            Ending net worth · age {data.projection_end_age}
          </Typography>
          {data.scenario_projections.map((p) => (
            <Typography key={p.settings.scenario_key} fontWeight={900}>
              {formatCrore(p.ending_total_net_worth_inr)}
            </Typography>
          ))}
          <Typography fontWeight={700}>₹15 Cr · Dec 2029</Typography>
          {data.scenario_projections.map((p) => (
            <Typography
              key={p.settings.scenario_key}
              color={
                p.december_2029_milestone?.on_track
                  ? "success.main"
                  : "error.main"
              }
              fontWeight={800}
            >
              {p.december_2029_milestone?.on_track ? "On track" : "Shortfall"} ·{" "}
              {formatCrore(p.december_2029_milestone?.projected_value_inr)}
            </Typography>
          ))}
        </Box>
      </Box>
      <Button
        sx={{ mt: 2 }}
        variant="contained"
        disabled={!dirty || disabled}
        onClick={() => onSave(toUpdate(draft))}
      >
        {disabled ? "Saving…" : "Save and recalculate"}
      </Button>
    </Box>
  );
};
