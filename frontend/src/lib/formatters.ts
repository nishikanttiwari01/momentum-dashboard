export const formatPct = (n: number) => `${(n * 100).toFixed(2)}%`
export const formatNum = (n: number) => new Intl.NumberFormat().format(n)
export const formatDate = (iso: string) => new Date(iso).toLocaleString()
