type NavPoint = { date: string; nav: number };
type Purchase = { date: string; nav: number; [key: string]: unknown };

const utcTime = (date: string) => Date.parse(`${date}T00:00:00Z`);

export function buildFundChartSeries(points: NavPoint[], purchases: Purchase[]) {
  return {
    prices: points.map(point => ({ time: utcTime(point.date), fullDate: point.date, nav: point.nav })),
    purchases: purchases.map(purchase => ({
      time: utcTime(purchase.date), fullDate: purchase.date,
      purchaseNav: purchase.nav, purchase,
    })),
  };
}

export function getFundChartDomain(prices: { time: number }[]): [number, number] {
  if (!prices.length) return [0, 0];
  return [prices[0].time, prices[prices.length - 1].time];
}
