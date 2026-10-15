// What `tagteam state --json` returns (the parts the plugin draws).
export type Window = { pct: number; countdown?: string; resetsAt?: string }
export type Usage = { fiveHour?: Window; sevenDay?: Window }
export type Sum = { total: number; output: number; cost: number; input: number; cacheWrite: number; cacheRead: number; messages: number }
export type Totals = { today: Sum; month: Sum; lifetime: Sum; since: string | null }
export type HeatCell = { date: string; total: number; output: number; cost: number; level: number; future: boolean }
export type Heatmap = {
  start: string; cells: HeatCell[]; yearTotal: number; yearCost: number; activeDays: number
  streak: number; longestStreak: number; busiest: { date: string; total: number } | null
}
export type Account = {
  number: number; email: string; label: string; alias?: string; active: boolean; disabled?: boolean
  usageStatus: string; usage: Usage | null; lastGoodUsage?: Usage; peakPct: number | null
  nearLimit: boolean; liveSessions: number; tokens: Totals
}
export type Alert = { kind: string; account: number; message: string; pct?: number; ko?: boolean; suggest?: { number: number; label: string; pct: number } | null }
export type Snapshot = {
  generatedAt: number; threshold: number; errors: string[]
  cswap: { installed: boolean; version: string | null }
  active: { number: number | null; label: string | null; email: string | null; managed: boolean }
  accounts: Account[]
  best: { number: number; label: string; pct: number } | null
  sessions: { pid: number; account: string | null; cwd: string; entrypoint?: string; status?: string }[]
  tokens: {
    totals: Record<string, Totals>; heatmap: Record<string, Heatmap>
    monthly: Record<string, { month: string; total: number; output: number; cost: number }[]>
    models: (Sum & { model: string })[]; projects: { project: string; total: number }[]; burnPerHour: number
  }
  alerts: Alert[]
  rules?: string
  mascot?: { palette: Record<string, string>; icon: string[] }
  setup: { id: string; ok: boolean; label: string; fix: string }[]
  auto: {
    enabled: boolean; mode: string; serviceInstalled: boolean
    settings: Record<string, string | number | boolean | null>
    recent: { event: string; ts: string; trigger?: string; from?: { number: number } | null; to?: { number: number; email: string } | null }[]
  }
}
export type Tab = 'overview' | 'setup' | 'auto'
export type Metric = 'total' | 'output' | 'cost'

declare module 'claude-code' {
  interface PluginState {
    'tag-team': {
      snap: Snapshot | null
      error: string | null
      busy: string | null
      note: string | null
      tab: Tab
      metric: Metric
      view: string
      confirm: string | null
      bandHidden: string | null
    }
  }
}
