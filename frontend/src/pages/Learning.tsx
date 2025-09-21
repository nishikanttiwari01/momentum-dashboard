// src/pages/Learning.tsx
import * as React from 'react';
import {
  Box,
  Container,
  Typography,
  Divider,
  Chip,
  Stack,
  Grid,
  Paper,
  List,
  ListItem,
  ListItemText,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableContainer,
} from '@mui/material';

const Section: React.FC<{ title: string; subtitle?: string; id?: string }>=({
  title,
  subtitle,
  id,
  children,
}) => (
  <Box id={id} sx={{ mb: 4 }}>
    <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: 0.2 }}>
      {title}
    </Typography>
    <Divider sx={{ mt: 1, mb: 2 }} />
    {subtitle ? (
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {subtitle}
      </Typography>
    ) : null}
    {children}
  </Box>
);

const BadgeChip = ({
  category,
  label,
}: {
  category: 'MOMENTUM' | 'BREAKOUT' | 'WATCH' | 'IGNORE';
  label: string;
}) => {
  const color =
    category === 'BREAKOUT'
      ? 'warning'
      : category === 'MOMENTUM'
      ? 'success'
      : category === 'IGNORE'
      ? 'error'
      : 'default';
  return <Chip size="small" color={color as any} label={label} sx={{ mr: 1, mb: 1 }} />;
};

const Bullet: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Stack direction="row" spacing={1} sx={{ mb: 0.5 }}>
    <Box
      sx={{
        mt: '8px',
        width: 6,
        height: 6,
        borderRadius: '50%',
        bgcolor: 'text.secondary',
        flexShrink: 0,
      }}
    />
    <Typography variant="body2">{children}</Typography>
  </Stack>
);

export default function Learning() {
  return (
    <Container maxWidth={false} sx={{ py: 4, px: { xs: 2, md: 4 } }}>
      {/* Title */}
      <Typography variant="h4" sx={{ fontWeight: 800, mb: 1 }}>
        How to Read the Dashboard
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        A practical, non-jargony guide to the indicators, scoring, badges, meters, and Next Action
        logic used in the right drawer.
      </Typography>

      {/* Quick TOC */}
      <Paper variant="outlined" sx={{ p: 2, mb: 4 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
          On this page
        </Typography>
        <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
          {[[ 'Quick Reference', '#quick-ref'], ['Indicators', '#indicators'], ['Scoring Model', '#scoring'], ['Badges', '#badges'], ['Meters', '#meters'], ['Method Pill & Next Action', '#next-action'], ['Data Quality & Alerts', '#quality'], ['Ranges at a Glance', '#ranges']].map(([label, href]) => (
            <Chip
              key={label}
              component="a"
              clickable
              href={href as string}
              size="small"
              variant="outlined"
              label={label}
            />
          ))}
        </Stack>
      </Paper>

      {/* Quick Reference Table */}
      <Section id="quick-ref" title="Indicators Quick Reference" subtitle="Plain-English cheat sheet for the most common numbers you’ll see.">
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="indicators quick reference">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 180, fontWeight: 700 }}>Indicator</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>What it means</TableCell>
                <TableCell sx={{ width: 260, fontWeight: 700 }}>Typical ranges / How to read</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>RSI(14)</TableCell>
                <TableCell>Momentum oscillator on a 0–100 scale.</TableCell>
                <TableCell>0–30 oversold · 40–60 balanced · 60–70 strong · &gt;70 extended</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>ADX(14)</TableCell>
                <TableCell>Trend strength (not direction).</TableCell>
                <TableCell>&lt;20 weak · 20–25 starting · 25–35 trending · 35–50 strong · &gt;50 very strong</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>RelVol(20)</TableCell>
                <TableCell>Participation vs 20‑day average volume.</TableCell>
                <TableCell>≈1× normal · 1.2–1.5× improving · &gt;1.5× strong · &gt;2× very strong</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>ATR %</TableCell>
                <TableCell>Average daily range as % of price (volatility).</TableCell>
                <TableCell>Low = calmer · High = bigger swings → wider stops/smaller size</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>EMA Fast / Slow</TableCell>
                <TableCell>Dynamic support/resistance (fast = e.g., EMA10).</TableCell>
                <TableCell>Fast above Slow = bullish · Far above Fast = extended; prefer pullback</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Proximity to 52W High</TableCell>
                <TableCell>How close price is to the 52‑week high.</TableCell>
                <TableCell>-5% to 0% near highs · &gt;0% already above highs · &lt;0% below highs</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Pivot Clear %</TableCell>
                <TableCell>How convincingly price is above a recent pivot.</TableCell>
                <TableCell>0–2% borderline · &gt;2% decisive breakout</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>OBV / vs MA</TableCell>
                <TableCell>Volume flow balance; above MA + up‑slope = accumulation.</TableCell>
                <TableCell>Up‑slope good · Down‑slope/Below MA = distribution risk</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Intraday Close vs Range</TableCell>
                <TableCell>Where close sits within the day’s high‑low.</TableCell>
                <TableCell>Near high = buyers in control · Near low = supply pressure</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      {/* Indicators */}
      <Section
        id="indicators"
        title="Indicators"
        subtitle="These are the core signals you’ll see in the drawer. Think of them as simple gauges telling you about trend, momentum, volatility, and participation."
      >
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                RSI(14)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                A momentum oscillator from 0–100.
              </Typography>
              <Bullet>{'< 30'}: “oversold”, often bouncy but can stay low.</Bullet>
              <Bullet>40–60: balanced / range-bound zone.</Bullet>
              <Bullet>60–70: strong momentum.</Bullet>
              <Bullet>{'> 70'}: “overbought”, extended — often needs a pullback.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                ADX(14)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Trend strength (not direction), 0–100.
              </Typography>
              <Bullet>{'< 20'}: weak / choppy.</Bullet>
              <Bullet>20–25: trend starting.</Bullet>
              <Bullet>25–35: trending.</Bullet>
              <Bullet>35–50: strong trend. {'> 50'}: very strong / potentially late.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                ATR%
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Average daily range as % of price (volatility proxy).
              </Typography>
              <Bullet>Low: calmer moves, easier stops.</Bullet>
              <Bullet>High: bigger swings; use wider stops or smaller size.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                EMA Fast / Slow
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Moving averages that act like “dynamic” support/resistance.
              </Typography>
              <Bullet>Price ≫ Fast EMA (e.g., EMA10): extended; prefer pullback to that EMA.</Bullet>
              <Bullet>Fast EMA {'>'} Slow EMA: bullish alignment.</Bullet>
              <Bullet>Cross-unders can warn on trend fade.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                RelVol(20)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Relative volume vs the 20-day average.
              </Typography>
              <Bullet>≈ 1×: typical participation.</Bullet>
              <Bullet>1.5×: healthy interest; {'> 2×'}: strong participation/accumulation.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Proximity to 52-Week High
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                How close we are to the 52W high (0% = at high; positive = above post-breakout; negative = below).
              </Typography>
              <Bullet>-5% to 0%: near highs; constructive for trend.</Bullet>
              <Bullet>{'> 0%'}: already broken out above highs (check risk/euphoria).</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Pivot &amp; Pivot Clear %
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Pivot = recent resistance. “Clear %” = how convincingly we’re above it.
              </Typography>
              <Bullet>0–2%: borderline breakout (can fail).</Bullet>
              <Bullet>{'> 2%'}: more decisive breakout.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                OBV / OBV slope / OBV vs MA
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                On-Balance Volume tracks whether up-days or down-days dominate volume.
              </Typography>
              <Bullet>Up-slope and OBV above its MA: accumulation bias.</Bullet>
              <Bullet>Down-slope or below MA: distribution risk.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Intraday Context
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Small helpers: gap-up %, and where the close sits in the day’s range.
              </Typography>
              <Bullet>Close near day high: buyers in control.</Bullet>
              <Bullet>Large gap without follow-through: susceptible to fade.</Bullet>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Scoring */}
      <Section
        id="scoring"
        title="Scoring Model"
        subtitle="We compute both a simple score and a fuller composite score. Only the 0–100 score is meant for comparison across symbols."
      >
        <Stack spacing={1.25}>
          <Typography variant="body2">
            <strong>Total Score (0–100)</strong> is what you should read in the UI. It blends:
          </Typography>
          <List dense>
            <ListItem>
              <ListItemText primary="Trend Rank" secondary="Captures EMA alignment, ADX, proximity to highs, etc." />
            </ListItem>
            <ListItem>
              <ListItemText primary="Breakout Quality" secondary="Pivot clearance %, follow-through, failure risk." />
            </ListItem>
            <ListItem>
              <ListItemText primary="Accumulation / RelVol" secondary="Participation via RelVol, OBV slope/MA." />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Data Quality Adjustments"
                secondary="Penalize stale data, gaps, poor liquidity; cap extreme euphoria."
              />
            </ListItem>
          </List>
          <Typography variant="body2">
            You may also see <strong>Simple Score (0–100)</strong> — a normalized version of a tiny rule-set, useful for
            sanity checks. It won’t match the full score because it uses fewer signals.
          </Typography>
          <Typography variant="body2">Typical thresholds:</Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mt: 0.5 }}>
            <BadgeChip category="MOMENTUM" label="≥ 85 Very High" />
            <BadgeChip category="MOMENTUM" label="75–84 High" />
            <BadgeChip category="WATCH" label="60–74 Watch" />
            <BadgeChip category="IGNORE" label="< 60 Ignore" />
          </Stack>
        </Stack>
      </Section>

      {/* Badges */}
      <Section
        id="badges"
        title="Badges"
        subtitle="Badges are quick labels. Momentum tier is always shown; Breakout appears only when strict conditions are met."
      >
        <Stack spacing={1}>
          <Typography variant="body2">
            <strong>Momentum (always)</strong> — tiered by total score:
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <BadgeChip category="MOMENTUM" label="🔥 High Momentum (75–84)" />
            <BadgeChip category="MOMENTUM" label="💥 Very High (≥ 85)" />
          </Stack>

          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>Breakout (conditional)</strong> — appears only if total score is high and key confirmations line up:
          </Typography>
          <List dense>
            <ListItem>
              <ListItemText primary="RSI ≥ 60" />
            </ListItem>
            <ListItem>
              <ListItemText primary="ADX ≥ 30" />
            </ListItem>
            <ListItem>
              <ListItemText primary="Pivot Clear % ≥ 2%" />
            </ListItem>
          </List>

          <Typography variant="body2" sx={{ mt: 1 }}>
            <strong>Watch / Ignore</strong> — reflects list-level filters (e.g., liquidity, staleness). These are “action” badges and can co-exist with Momentum.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <BadgeChip category="WATCH" label="👀 Watch" />
            <BadgeChip category="IGNORE" label="🚫 Ignore" />
          </Stack>
        </Stack>
      </Section>

      {/* Meters */}
      <Section id="meters" title="Meters (Analog Gauges)" subtitle="Two semi-circular meters summarize conditions from 0–100.">
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Risk
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Green→Red. Higher = harder to manage: wide ATR%, extended far above EMA, large gaps, thin liquidity.
              </Typography>
              <Bullet>0–30: gentle.</Bullet>
              <Bullet>30–60: normal swing risk.</Bullet>
              <Bullet>60–100: elevated/extended; prefer pullbacks or smaller size.</Bullet>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Euphoria
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Captures “chase” risk: price distance from fast EMA, RSI heat, and participation spikes.
              </Typography>
              <Bullet>0–30: calm.</Bullet>
              <Bullet>30–60: strong but reasonable.</Bullet>
              <Bullet>60–100: extended/late; pullback entries preferred.</Bullet>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Method & Next Action */}
      <Section
        id="next-action"
        title="Method Pill & Next Action"
        subtitle="Explains what the pill means and how to read the guidance line with its reference chips."
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          Method Pill
        </Typography>
        <Typography variant="body2" sx={{ mb: 2 }}>
          A tiny label summarizing the rule driving the current guidance: <strong>EMA10</strong> (hold while above
          EMA10), <strong>EMA20</strong> (slower), <strong>BREAKOUT</strong> (pivot-based), <strong>PULLBACK</strong>
          (prefer buy near EMA after extension), etc.
        </Typography>

        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          “Next Action” Line
        </Typography>
        <List dense sx={{ mb: 1 }}>
          <ListItem>
            <ListItemText
              primary="Text"
              secondary="Short instruction like: “Hold (above EMA10)” or “Wait for pullback to EMA10.”"
            />
          </ListItem>
          <ListItem>
            <ListItemText primary="EMAₙ = value" secondary="The exact moving average used (e.g., EMA10=₹123.45)." />
          </ListItem>
          <ListItem>
            <ListItemText primary="Suggested Entry / Band" secondary="A price or range for preferred entries when extended." />
          </ListItem>
          <ListItem>
            <ListItemText primary="Entry Type" secondary="PULLBACK or BREAKOUT, matching the method." />
          </ListItem>
          <ListItem>
            <ListItemText primary="Reason" secondary="Plain-English note (e.g., ‘Extended; prefer pullback to EMA10’)." />
          </ListItem>
        </List>

        <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            <strong>Example</strong>
          </Typography>
          <Typography variant="body2">
            Method: <Chip size="small" color="info" label="EMA10" sx={{ mx: 0.5 }} /> Next Action: <strong>Hold (above EMA10)</strong>
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mt: 1 }}>
            <Chip size="small" label="EMA10 = ₹123.45" />
            <Chip size="small" label="Suggested Entry ₹120–₹122" />
            <Chip size="small" label="Type: PULLBACK" />
            <Chip size="small" label="Reason: Extended vs fast EMA" />
          </Stack>
        </Paper>
      </Section>

      {/* Data Quality & Alerts */}
      <Section id="quality" title="Data Quality & Alerts" subtitle="Why some rows get penalties, and common alert ideas.">
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Quality Flags
              </Typography>
              <Bullet>Stale data or gaps can reduce score and hide breakouts.</Bullet>
              <Bullet>Low liquidity raises execution risk (also increases Risk meter).</Bullet>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Alerts (examples)
              </Typography>
              <Bullet>Price crosses key EMAₙ.</Bullet>
              <Bullet>Breaks above pivot / 52W high.</Bullet>
              <Bullet>Stop-loss touched or breakeven activated.</Bullet>
              <Bullet>RelVol spike above threshold.</Bullet>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Ranges at a Glance */}
      <Section id="ranges" title="Ranges at a Glance">
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                RSI
              </Typography>
              <Typography variant="body2">
                0–30 oversold · 40–60 balanced · 60–70 strong · {'>'}70 extended
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                ADX
              </Typography>
              <Typography variant="body2">
                {'<'}20 weak · 20–25 starting · 25–35 trending · 35–50 strong · {'>'}50 very strong
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                RelVol(20)
              </Typography>
              <Typography variant="body2">
                ≈1× normal · 1.2–1.5× improving · {'>'}1.5× strong · {'>'}2× very strong
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                Pivot Clear %
              </Typography>
              <Typography variant="body2">0–2% borderline · {'>'}2% decisive</Typography>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Footer */}
      <Box sx={{ mt: 6 }}>
        <Divider sx={{ mb: 2 }} />
        <Typography variant="caption" color="text.secondary">
          This page summarizes the current model and UI behavior. Some thresholds may evolve as the scoring improves.
        </Typography>
      </Box>
    </Container>
  );
}
