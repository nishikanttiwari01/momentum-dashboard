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

const Section: React.FC<{ title: string; subtitle?: string; id?: string }> = ({
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
  <Stack direction="row" spacing={1} sx={{ mb: 0.6 }}>
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
        A practical guide in plain English. This page explains the indicators, scoring, badges,
        meters, method pill, and “Next Action” logic you’ll see in the right drawer.
      </Typography>

      {/* Quick TOC */}
      <Paper variant="outlined" sx={{ p: 2, mb: 4 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
          On this page
        </Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          {[
            ['Quick Reference', '#quick-ref'],
            ['Indicators', '#indicators'],
            ['Scoring Model', '#scoring'],
            ['Meters', '#meters'],
            ['Method Pill & Next Action', '#next-action'],
            ['All Actions (When & Why)', '#actions'],
            ['Glossary (Plain English)', '#glossary'],
            ['Ranges at a Glance', '#ranges'],
          ].map(([label, href]) => (
            <Chip key={label} component="a" clickable href={href as string} size="small" variant="outlined" label={label} />
          ))}
        </Stack>
      </Paper>

      {/* Indicators Quick Reference */}
      <Section
        id="quick-ref"
        title="Indicators Quick Reference"
        subtitle="Cheat sheet for the most common numbers you’ll see."
      >
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="indicators quick reference">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 180, fontWeight: 700 }}>Indicator</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>What it means</TableCell>
                <TableCell sx={{ width: 320, fontWeight: 700 }}>Typical ranges / How to read</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>RSI(14)</TableCell>
                <TableCell>Momentum on a 0–100 scale.</TableCell>
                <TableCell>0–30 oversold · 40–60 balanced · 60–70 strong · &gt;70 extended</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>ADX(14)</TableCell>
                <TableCell>Trend strength (not direction).</TableCell>
                <TableCell>&lt;20 weak · 20–25 starting · 25–35 trending · 35–50 strong · &gt;50 very strong</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>RelVol(20)</TableCell>
                <TableCell>Participation vs 20-day average volume.</TableCell>
                <TableCell>≈1× normal · 1.2–1.5× improving · &gt;1.5× strong · &gt;2× very strong</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>ATR %</TableCell>
                <TableCell>Average daily range as % of price (volatility).</TableCell>
                <TableCell>Higher ATR% = bigger swings → wider stops/smaller size</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>EMA (Fast / Slow)</TableCell>
                <TableCell>
                  Dynamic rails. <strong>Fast</strong> reacts quicker (e.g., <strong>EMA8</strong>); 
                  <strong>Slow</strong> is steadier (e.g., <strong>EMA10–20</strong>).
                </TableCell>
                <TableCell>
                  Fast &gt; Slow = bullish; far above Fast = extended (prefer pullback). 
                  The app usually uses Fast=8 and Slow=10 unless configured otherwise.
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Proximity to 52W High</TableCell>
                <TableCell>How close price is to the 52-week high.</TableCell>
                <TableCell>-5% to 0% near highs · &gt;0% above highs · &lt;0% below highs</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Pivot Clear %</TableCell>
                <TableCell>How convincingly price is above a recent pivot.</TableCell>
                <TableCell>0–2% borderline · &gt;2% decisive breakout</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Close vs Day Range</TableCell>
                <TableCell>Where close sits within today’s high-low.</TableCell>
                <TableCell>Near high = buyers in control · Near low = supply pressure</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      {/* Indicators (expanded, in plain language) */}
      <Section
        id="indicators"
        title="Indicators"
        subtitle="Simple gauges telling you about trend, momentum, volatility, and participation."
      >
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>RSI(14)</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Momentum oscillator from 0–100. Higher = faster recent gains.
              </Typography>
              <Bullet>{'< 30'}: “oversold”; bouncy but can stay low.</Bullet>
              <Bullet>40–60: balanced/range-bound.</Bullet>
              <Bullet>60–70: strong momentum.</Bullet>
              <Bullet>{'> 70'}: hot/extended; prefer pullbacks.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>ADX(14)</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Strength of the trend (not up/down direction).
              </Typography>
              <Bullet>{'< 20'}: weak/choppy.</Bullet>
              <Bullet>20–25: trend starting.</Bullet>
              <Bullet>25–35: trending.</Bullet>
              <Bullet>35–50 strong; {'> 50'} very strong/late.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>ATR%</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Typical daily swing size. Guides position sizing and stop width.
              </Typography>
              <Bullet>Low ATR%: calmer tape; normal sizing.</Bullet>
              <Bullet>High ATR%: bigger whipsaws; reduce size/widen stops.</Bullet>
            </Paper>
          </Grid>

          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>EMA Fast / Slow</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Moving averages that act like “dynamic rails”. Fast = EMA8/10; Slow = longer EMA.
              </Typography>
              <Bullet>Price far above Fast EMA → extended → pullback setup.</Bullet>
              <Bullet>Fast EMA {'>'} Slow EMA → supportive trend.</Bullet>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Scoring Model */}
      <Section
        id="scoring"
        title="Scoring Model (0–100)"
        subtitle="Grades the sustainability of a move, not just today’s % change."
      >
        <Stack spacing={1.25}>
          <Typography variant="body2">
            <strong>Total Score</strong> blends four ideas:
          </Typography>
          <List dense>
            <ListItem>
              <ListItemText
                primary="Trend Quality"
                secondary="Do moving averages line up? Is ADX firm? Are we near 52-week highs (healthy) or far from them?"
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Breakout Quality"
                secondary="How clean is the pivot break? Pivot Clear %, follow-through, and not too extended."
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Participation"
                secondary="RelVol & volume flow (OBV). Higher participation = more trustworthy moves."
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Risk & Data Adjustments"
                secondary="Penalize stale data/gaps/liquidity issues and extreme euphoria; normalize across symbols."
              />
            </ListItem>
          </List>
          <Typography variant="body2">Rule-of-thumb bands:</Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mt: 0.5 }}>
            <BadgeChip category="MOMENTUM" label="≥ 85 Very High" />
            <BadgeChip category="MOMENTUM" label="75–84 High" />
            <BadgeChip category="WATCH" label="60–74 Watch" />
            <BadgeChip category="IGNORE" label="< 60 Low" />
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Note: Big one-day winners with weak ADX or very extended pivots may still score mid-range. That’s by design.
          </Typography>
        </Stack>
      </Section>

      {/* Meters */}
      <Section id="meters" title="Meters (Analog Gauges)" subtitle="Two quick dials summarizing conditions from 0–100.">
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Risk</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Green→Red. Higher = harder to manage: wide ATR%, far above EMA, large gaps, thin liquidity.
              </Typography>
              <Bullet>0–30: gentle.</Bullet>
              <Bullet>30–60: normal swing risk.</Bullet>
              <Bullet>60–100: elevated/extended → prefer pullbacks or smaller size.</Bullet>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Euphoria</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Captures “chase” risk: hot RSI, firm ADX, strong participation, distance from fast EMA.
              </Typography>
              <Bullet>0–30: calm.</Bullet>
              <Bullet>30–60: strong but reasonable.</Bullet>
              <Bullet>60–100: extended/late → prefer pullbacks.</Bullet>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Method Pill & Next Action */}
      <Section
        id="next-action"
        title="Method Pill & Next Action"
        subtitle="The pill tells you the rule in force; the line tells you what to do."
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          Method Pill (what it means)
        </Typography>
        <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 140, fontWeight: 700 }}>Pill</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Meaning</TableCell>
                <TableCell sx={{ width: 220, fontWeight: 700 }}>Exit anchor</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell><Chip size="small" label="EMA8" color="info" /></TableCell>
                <TableCell>Hot tape (euphoria on). Faster rail; tighter behavior.</TableCell>
                <TableCell>Hold while above <strong>EMA8</strong>.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><Chip size="small" label="ATRx" color="secondary" /></TableCell>
                <TableCell>
                  ATR-based trailing method (a “Chandelier” stop). Used in high-volatility or whipsaw-prone names.
                </TableCell>
                <TableCell>
                  Hold while above the <strong>ATR×K</strong> trail (e.g., K=2.0; tighter K≈1.4 in euphoria).
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell><Chip size="small" label="EMA10" color="info" /></TableCell>
                <TableCell>Normal momentum regime. Default rail.</TableCell>
                <TableCell>Hold while above <strong>EMA10</strong>.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><Chip size="small" label="BREAKOUT" /></TableCell>
                <TableCell>Pivot-based entry; needs decisive clearance and participation.</TableCell>
                <TableCell>N/A (pre-entry context).</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><Chip size="small" label="PULLBACK" /></TableCell>
                <TableCell>Extended vs fast EMA; prefer buy near the EMA band.</TableCell>
                <TableCell>N/A (pre-entry context).</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TableContainer>

        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          “Next Action” at a Glance
        </Typography>
        <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 150, fontWeight: 700 }}>Action</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>When it appears</TableCell>
                <TableCell sx={{ width: 260, fontWeight: 700 }}>What to do / Notes</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell><strong>BUY_BREAKOUT</strong></TableCell>
                <TableCell>Price clears pivot decisively; score/ADX/RelVol confirm; not overly extended.</TableCell>
                <TableCell>Buy the break or quick reclaim. Ref shows the pivot <em>level</em>.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><strong>BUY_PULLBACK</strong></TableCell>
                <TableCell>Move is hot/extended vs fast EMA.</TableCell>
                <TableCell>Wait for dip toward EMA band. Refs show a price <em>range</em>.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><strong>BUY_STARTER</strong></TableCell>
                <TableCell>Early strength (RelVol spike, ADX building) but not fully confirmed.</TableCell>
                <TableCell>Small “toe-in” position; typically near current price/EMA.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><strong>WATCH</strong></TableCell>
                <TableCell>Soft gates fail (e.g., low score/ADX/RelVol or below pivot).</TableCell>
                <TableCell>Observe only; we intentionally avoid showing entry bands here.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><strong>HOLD</strong></TableCell>
                <TableCell>In position; price above exit rail.</TableCell>
                <TableCell>Hold while above EMAₙ (pill tells which EMA).</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><strong>HOLD_BREAKEVEN</strong></TableCell>
                <TableCell>In position; stop has been raised to ≥ entry.</TableCell>
                <TableCell>Risk removed; manage against the active rail.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><strong>SELL_NOW</strong></TableCell>
                <TableCell>Stop hit (or hard rule triggered).</TableCell>
                <TableCell>Exit immediately; ref shows the stop that was hit.</TableCell>
              </TableRow>
              <TableRow>
                <TableCell><strong>SELL_TOMORROW</strong></TableCell>
                <TableCell>Daily/EOD context: close is below the active EMA rail.</TableCell>
                <TableCell>Plan exit at next close unless reclaimed.</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TableContainer>
      </Section>

      {/* All Actions - compact bullets for non-traders */}
      <Section
        id="actions"
        title="All Actions (When & Why)"
        subtitle="If you only read one section, read this."
      >
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Before a trade</Typography>
              <Bullet><strong>BUY_BREAKOUT:</strong> Over the pivot with confirmation (score/ADX/RelVol). Not too stretched.</Bullet>
              <Bullet><strong>BUY_PULLBACK:</strong> Too hot above EMA → buy nearer the EMA band.</Bullet>
              <Bullet><strong>BUY_STARTER:</strong> Signs of life; small size to get started.</Bullet>
              <Bullet><strong>WATCH:</strong> Not enough evidence (yet) or below pivot → hands in pockets.</Bullet>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>After you’re in</Typography>
              <Bullet><strong>HOLD:</strong> Price above the active EMA rail → keep holding.</Bullet>
              <Bullet><strong>HOLD_BREAKEVEN:</strong> Stop raised to entry or higher → risk is off.</Bullet>
              <Bullet><strong>SELL_NOW:</strong> Stop hit → exit immediately.</Bullet>
              <Bullet><strong>SELL_TOMORROW:</strong> EOD close is below rail → exit on next close unless reclaimed.</Bullet>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Glossary */}
      <Section
        id="glossary"
        title="Glossary (Plain English)"
        subtitle="Common terms you’ll see in the app, explained simply."
      >
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Bullet><strong>EMA (Exponential Moving Average):</strong> Running average that follows price closely. We use fast rails like EMA8/EMA10.</Bullet>
              <Bullet><strong>RSI:</strong> Speed of recent gains/losses; over 70 = “hot”.</Bullet>
              <Bullet><strong>ADX:</strong> Strength of the trend; over 25 = proper trend.</Bullet>
              <Bullet><strong>ATR%:</strong> Typical day’s swing as % of price; higher = choppier.</Bullet>
              <Bullet><strong>RelVol:</strong> Today’s volume vs 20-day average; above 1.5× = strong interest.</Bullet>
              <Bullet><strong>Pivot:</strong> Recent ceiling; clearing it is a breakout.</Bullet>
              <Bullet><strong>Pivot Clear %:</strong> How far above pivot we are (higher = cleaner, but too high = extended).</Bullet>
              <Bullet><strong>Proximity to 52W High:</strong> How close we are to the yearly high; near highs is constructive.</Bullet>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Bullet><strong>Euphoria:</strong> Hot tape condition (RSI/ADX/participation). We switch to EMA8 behavior.</Bullet>
              <Bullet><strong>Breakeven:</strong> When the stop is moved up to your entry or higher.</Bullet>
              <Bullet><strong>Stop (Chandelier/ATR):</strong> Trailing floor based on volatility (ATR). Wider in choppy names.</Bullet>
              <Bullet><strong>Close vs Range:</strong> Whether we finished near the day’s high or low.</Bullet>
              <Bullet><strong>Base Length (bars):</strong> How many days we’ve consolidated; longer bases are sturdier.</Bullet>
              <Bullet><strong>Starter:</strong> Small first buy to test the waters; add only if the thesis improves.</Bullet>
              <Bullet><strong>Reclaim:</strong> Price falls below a level then gets back above it (e.g., reclaim pivot/EMA).</Bullet>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Ranges at a Glance */}
      <Section id="ranges" title="Ranges at a Glance">
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>RSI</Typography>
              <Typography variant="body2">0–30 oversold · 40–60 balanced · 60–70 strong · {'>'}70 extended</Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>ADX</Typography>
              <Typography variant="body2">{'<'}20 weak · 20–25 starting · 25–35 trending · 35–50 strong · {'>'}50 very strong</Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>RelVol(20)</Typography>
              <Typography variant="body2">≈1× normal · 1.2–1.5× improving · {'>'}1.5× strong · {'>'}2× very strong</Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Pivot Clear %</Typography>
              <Typography variant="body2">0–2% borderline · {'>'}2% decisive</Typography>
            </Paper>
          </Grid>
        </Grid>
      </Section>

      {/* Footer */}
      <Box sx={{ mt: 6 }}>
        <Divider sx={{ mb: 2 }} />
        <Typography variant="caption" color="text.secondary">
          This page summarizes the current model and UI behavior. Thresholds may evolve as we refine scoring and risk management.
        </Typography>
      </Box>
    </Container>
  );
}
