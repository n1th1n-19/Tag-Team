import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Account, Heatmap, Metric, Snapshot, Sum, Tab } from '../types'

const PANE = 'tag-team'
const snap = atom({ plugin: 'tag-team', key: 'snap' } as const, null)
const error = atom({ plugin: 'tag-team', key: 'error' } as const, null)
const busy = atom({ plugin: 'tag-team', key: 'busy' } as const, null)
const note = atom({ plugin: 'tag-team', key: 'note' } as const, null)
const tab = atom({ plugin: 'tag-team', key: 'tab' } as const, 'overview' as Tab)
const metric = atom({ plugin: 'tag-team', key: 'metric' } as const, 'total' as Metric)
const view = atom({ plugin: 'tag-team', key: 'view' } as const, 'all')
const confirm = atom({ plugin: 'tag-team', key: 'confirm' } as const, null)
const bandHidden = atom({ plugin: 'tag-team', key: 'bandHidden' } as const, null)

// Match-history heat: cold canvas to hot gold (retro ring palette).
const RAMP = ['#3b3f52', '#6b3a3a', '#a83a3a', '#d94141', '#f2c14e']
const RAMP_RGB = [0x3b3f52, 0x6b3a3a, 0xa83a3a, 0xd94141, 0xf2c14e]

export const fmt = (n: number): string => {
  for (const [u, s] of [['B', 1e9], ['M', 1e6], ['K', 1e3]] as const) if (Math.abs(n) >= s) return (n / s).toFixed(1) + u
  return String(Math.round(n || 0))
}
const money = (n: number) => '$' + (n || 0).toFixed(2)
/** Where the token numbers come from, and how much is cache reads (the same context re-read every turn). */
const scoreNote = (l: Sum) => 'Claude Code on this computer only' + (l.total ? ` · ${Math.round((100 * l.cacheRead) / l.total)}% cache reads · ${fmt(l.total - l.cacheRead)} fresh` : '')
export const bar = (pct: number, width = 16) => {
  const filled = Math.max(0, Math.min(width, Math.round((pct / 100) * width)))
  return '█'.repeat(filled) + '░'.repeat(width - filled)
}
/** Fighting-game life bar: full when fresh, drains as the limit is used. */
export const life = (pct: number, width = 16) => bar(100 - pct, width)

/** The Figma mascot from the snapshot, as an SVG (editors) or half-block Raster cells (terminal). */
export function mascotSvg(m: { palette: Record<string, string>, icon: string[] }, scale = 3): string {
  const rows = m.icon.filter(r => r.replace(/\./g, '')), w = rows[0]?.length ?? 0
  let rects = ''
  rows.forEach((row, y) => [...row].forEach((ch, x) => { if (ch !== '.') rects += `<rect x="${x}" y="${y}" width="1" height="1" fill="${m.palette[ch]}"/>` }))
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${rows.length}" width="${w * scale}" height="${rows.length * scale}" shape-rendering="crispEdges">${rects}</svg>`
}
export function mascotRaster(m: { palette: Record<string, string>, icon: string[] }) {
  const rows = m.icon.filter(r => r.replace(/\./g, ''))
  if (rows.length % 2) rows.push('.'.repeat(rows[0]?.length ?? 0))
  const cols = rows[0]?.length ?? 0, lines = rows.length / 2
  const words = new Uint32Array(cols * lines * 3)
  const DEFAULT = 0x01000000
  const rgb = (ch: string) => ch === '.' ? DEFAULT : parseInt((m.palette[ch] ?? '#000000').slice(1), 16)
  for (let y = 0; y < lines; y++) for (let x = 0; x < cols; x++) {
    const top = rows[y * 2]?.[x] ?? '.', bot = rows[y * 2 + 1]?.[x] ?? '.', i = (y * cols + x) * 3
    if (top === '.' && bot === '.') { words[i] = 32; words[i + 1] = DEFAULT; words[i + 2] = DEFAULT }
    else if (top === '.') { words[i] = 0x2584; words[i + 1] = rgb(bot); words[i + 2] = DEFAULT }
    else { words[i] = 0x2580; words[i + 1] = rgb(top); words[i + 2] = rgb(bot) }
  }
  return { columns: cols, rows: lines, cells: b64(new Uint8Array(words.buffer)) }
}
const usageOf = (a: Account) => a.usage || a.lastGoodUsage || {}

/** Quartile level of a value among the year's active days, GitHub-style. */
export function levels(hm: Heatmap, m: Metric): (v: number) => number {
  const vals = hm.cells.filter(c => !c.future && c[m] > 0).map(c => c[m]).sort((a, b) => a - b)
  const q = vals.length ? [0.25, 0.5, 0.75].map(p => vals[Math.floor((vals.length - 1) * p)]) : [0, 0, 0]
  return v => (v <= 0 ? 0 : 1 + q.filter(x => x !== undefined && v > x).length)
}

export function heatSvg(hm: Heatmap, m: Metric): string {
  const level = levels(hm, m)
  const C = 12, L = 28, T = 14, weeks = Math.ceil(hm.cells.length / 7)
  const months = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ')
  let s = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${L + weeks * C} ${T + 7 * C}" font-family="sans-serif" font-size="9" fill="#8b98a5">`
  let lastMonth = -1
  for (let w = 0; w < weeks; w++) {
    const month = Number(hm.cells[w * 7]?.date.slice(5, 7)) - 1
    if (month !== lastMonth && w < weeks - 2) s += `<text x="${L + w * C}" y="9">${months[month]}</text>`
    lastMonth = month
    for (let r = 0; r < 7; r++) {
      const c = hm.cells[w * 7 + r]
      if (!c || c.future) continue
      const v = c[m]
      const label = m === 'cost' ? money(v) : `${fmt(v)} tokens`
      s += `<rect x="${L + w * C}" y="${T + r * C}" width="10" height="10" fill="${RAMP[level(v)] ?? RAMP[0]}"><title>${c.date}: ${label}</title></rect>`
    }
  }
  ;['', 'Mon', '', 'Wed', '', 'Fri', ''].forEach((n, r) => { if (n) s += `<text x="0" y="${T + r * C + 8}">${n}</text>` })
  return s + '</svg>'
}

function b64(bytes: Uint8Array): string {
  const anyBytes = bytes as Uint8Array & { toBase64?: () => string }
  if (typeof anyBytes.toBase64 === 'function') return anyBytes.toBase64()
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(bin)
}

/** Terminal heatmap: one Raster, each day a colored ■ plus a gap. Shows the weeks that fit. */
export function heatRaster(hm: Heatmap, m: Metric, columns: number) {
  const level = levels(hm, m)
  const allWeeks = Math.ceil(hm.cells.length / 7)
  const weeks = Math.max(4, Math.min(allWeeks, Math.floor((columns - 4) / 2)))
  const first = allWeeks - weeks
  const cols = 4 + weeks * 2, rows = 7
  const words = new Uint32Array(cols * rows * 3)
  const DEFAULT = 0x01000000
  const put = (x: number, y: number, ch: string, fg: number) => {
    const i = (y * cols + x) * 3
    words[i] = ch.codePointAt(0) ?? 32; words[i + 1] = fg; words[i + 2] = DEFAULT
  }
  for (let y = 0; y < rows; y++) {
    const name = (['', 'Mon', '', 'Wed', '', 'Fri', ''][y] ?? '').padEnd(4)
    for (let x = 0; x < 4; x++) put(x, y, name[x] ?? ' ', DEFAULT)
    for (let w = 0; w < weeks; w++) {
      const c = hm.cells[(first + w) * 7 + y]
      const lv = c && !c.future ? level(c[m]) : -1
      put(4 + w * 2, y, lv < 0 ? ' ' : lv === 0 ? '·' : '■', lv <= 0 ? DEFAULT : RAMP_RGB[lv] ?? DEFAULT)
      put(5 + w * 2, y, ' ', DEFAULT)
    }
  }
  return { columns: cols, rows, cells: b64(new Uint8Array(words.buffer)) }
}

let BIN = 'tagteam'
let REFRESH_MS = 60_000
let inflight = false
let lastRefresh = 0
let alerted: string | null = null

let RESOLVED: { bin: string, cwd?: string } | null = null

// Absolute path from PATH only, run from home: Windows would otherwise try the project folder first.
async function resolveBin($: any): Promise<{ bin: string, cwd?: string }> {
  if (RESOLVED) return RESOLVED
  const path = String((await $.env.get('PATH')) ?? '')
  const win = (await $.env.get('OS')) === 'Windows_NT' || /^[A-Za-z]:\\/.test(path)
  const home = (win ? await $.env.get('USERPROFILE') : await $.env.get('HOME')) || undefined
  const isAbs = (p: string) => (win ? /^[A-Za-z]:[\\/]/.test(p) : p.startsWith('/'))
  if (isAbs(BIN)) return (RESOLVED = { bin: BIN, cwd: home })
  const exts = win ? ['.exe', '.cmd', '.bat'] : ['']
  for (const dir of path.split(win ? ';' : ':')) {
    if (!dir || !isAbs(dir)) continue
    for (const ext of exts) {
      const file = `${dir.replace(/[\\/]+$/, '')}${win ? '\\' : '/'}${BIN}${ext}`
      try { if (await $.fs.exists(file)) return (RESOLVED = { bin: file, cwd: home }) } catch { /* keep looking */ }
    }
  }
  throw new Error(`Can't find "${BIN}" on PATH. Install Tag Team (see README) or set tagteamPath in /config.`)
}

async function tagteam($: any, args: string[], stdin?: string): Promise<any> {
  const { bin, cwd } = await resolveBin($)
  const res = await $.process.run([bin, ...args], { timeoutMs: 120_000, stdin, cwd, env: { NO_COLOR: '1' } })
  const text = res.stdout.trim()
  let data: any = null
  try { data = text ? JSON.parse(text.split('\n').pop() as string) : null } catch { /* plain text */ }
  if (res.exitCode !== 0 || (data && data.ok === false)) throw new Error(data?.error || res.stderr.trim() || text || `${BIN} exited ${res.exitCode}`)
  return data ?? { message: text }
}

async function refresh($: any) {
  if (inflight) return
  inflight = true
  lastRefresh = await $.clock.now()
  try {
    const s: Snapshot = await tagteam($, ['state'])
    await update($, snap, () => s)
    await update($, error, () => null)
    afterRefresh($, s)
  } catch (err) {
    const msg = String((err as Error).message || err)
    await update($, error, () => msg.includes('ENOENT') || msg.includes('not found')
      ? `Can't run "${BIN}". Install Tag Team (see README) or set tagteamPath in /config.` : msg)
  } finally {
    inflight = false
  }
}

function afterRefresh($: any, s: Snapshot) {
  const a = s.accounts.find(x => x.active)
  const u = a ? usageOf(a) : {}
  const parts = [`[IN] ${s.active.label || 'nobody'}`]
  if (u.fiveHour) parts.push(`${life(u.fiveHour.pct, 5).replace(/█/g, '▮').replace(/░/g, '▯')} stamina ${Math.round(u.fiveHour.pct)}%`)
  if (u.sevenDay) parts.push(`endurance ${Math.round(u.sevenDay.pct)}%`)
  parts.push(`tonight ${fmt(s.tokens.totals.all?.today.total ?? 0)}`)
  if (s.auto.enabled) parts.push('blind tag')
  if (s.alerts.some(x => x.kind === 'near-limit')) parts.push('TAG ME!')
  $.ui.status(parts.join(' · '))

  const near = s.alerts.find(x => x.kind === 'near-limit')
  const key = near ? `${near.account}:${Math.floor((near.pct ?? 0) / 5)}` : null
  if (near && key !== alerted) {
    const hint = near.suggest ? ` ${near.suggest.label} is fresh (${Math.round(near.suggest.pct)}%). /tag-out to tag them in.` : ''
    $.ui.toast(`${near.ko ? 'DOWN FOR THE COUNT' : 'REACH FOR THE TAG'}: ${near.message}.${hint}`)
    void $.ui.notify(`${near.message}.${hint}`, { title: 'Tag Team: TAG ME!' }).catch(() => {})
  }
  alerted = key
  if (s.auto.enabled && !s.auto.serviceInstalled) void autoTick($)
}

async function autoTick($: any) {
  try {
    const r = await tagteam($, ['blind-tag', 'once', '--json'])
    if (String(r.message || '').startsWith('Blind tag!')) {
      $.ui.toast(`Tag Team: ${r.message}`)
      await refresh($)
    }
  } catch { /* the next tick retries; cswap logs its own errors */ }
}

async function act($: any, label: string, args: string[], stdin?: string) {
  await update($, busy, () => label)
  try {
    const r = await tagteam($, args, stdin)
    await update($, note, () => r.message || `${label}: done`)
    $.ui.toast(r.message || `${label}: done`)
  } catch (err) {
    await update($, note, () => `${label} failed: ${(err as Error).message}`)
  } finally {
    await update($, busy, () => null)
    await refresh($)
  }
}

function open($: any) {
  // Popup manners: takes the keyboard when it opens, Esc closes it.
  return $.ui.open({ id: PANE, title: 'Tag Team Wrestling', focus: true, closeOnEscape: true, columns: 100, rows: 44 })
}

function alertsView($: any, ui: any, s: Snapshot) {
  const { Box, Text, Button } = ui
  return s.alerts.map(a => (
    <Box key={`alert-${a.kind}-${a.account}`} flexDirection="row" flexWrap="wrap" gap={1} alignItems="center">
      <Text color={a.kind === 'near-limit' ? 'error' : 'warning'} bold={a.kind === 'near-limit'}>
        {a.kind === 'near-limit' ? (a.ko ? 'DOWN FOR THE COUNT! ' : 'REACH FOR THE TAG! ') : '⚠ '}{a.message}
      </Text>
      {a.kind === 'near-limit' && a.suggest && (
        <Button key={`alert-sw-${a.account}`} variant="primary" label={`TAG ME > ${a.suggest.label}`}
          onPress={() => act($, 'Tagging', ['tag-in', String(a.suggest!.number), '--json'])} />
      )}
      {a.kind === 'near-limit' && (
        <Button key={`alert-best-${a.account}`} label="Hot tag: best" onPress={() => act($, 'Hot tag', ['tag-out', '--json'])} />
      )}
    </Box>
  ))
}

async function overview($: any, ui: any, e: any, s: Snapshot, width: number) {
  const { Box, Text, Button } = ui
  const m = await read($, metric)
  const v = await read($, view)
  const key = s.tokens.heatmap[v] ? v : 'all'
  const hm = (s.tokens.heatmap[key] ?? s.tokens.heatmap.all)!
  const t = (s.tokens.totals[key] ?? s.tokens.totals.all)!
  const barW = width >= 90 ? 16 : 10

  const lanes = s.accounts.map(a => {
    const u = usageOf(a)
    const five = u.fiveHour, seven = u.sevenDay
    const ko = (five?.pct ?? 0) >= 100 || (seven?.pct ?? 0) >= 100
    const meters = five || seven
      ? `STAMINA ${life(five?.pct ?? 0, barW)} ${String(Math.round(five?.pct ?? 0)).padStart(3)}%  ENDURANCE ${life(seven?.pct ?? 0, Math.round(barW / 2))} ${String(Math.round(seven?.pct ?? 0)).padStart(3)}%${ko ? '  K.O.' : ''}`
      : a.usageStatus.replace(/_/g, ' ')
    return (
      <Box key={`acct-${a.number}`} flexDirection="row" flexWrap="wrap" gap={1} alignItems="center">
        <Text bold={a.active} color={a.nearLimit ? 'warning' : a.active ? 'success' : undefined}>
          {a.active ? '▶ [IN]   ' : a.disabled ? '  [BENCH]' : '  [APRON]'} {a.label.slice(0, 16).padEnd(16)}
        </Text>
        <Text color={a.nearLimit ? 'warning' : undefined}>{meters}</Text>
        <Text dimColor>tonight {fmt(a.tokens.today.total)} · month {fmt(a.tokens.month.total)}{a.liveSessions ? ` · ${a.liveSessions} in progress` : ''}{five?.countdown ? ` · stamina back in ${five.countdown}` : ''}</Text>
        {a.active
          ? <Text color="success">IN THE RING</Text>
          : a.disabled ? <Text dimColor>benched</Text>
          : <Button key={`sw-${a.number}`} variant={a.nearLimit ? undefined : 'primary'} label="Tag in"
              onPress={() => act($, `Tagging in ${a.label}`, ['tag-in', String(a.number), '--json'])} />}
      </Box>
    )
  })

  const heat = e.surface === 'terminal'
    ? (() => { const r = heatRaster(hm, m, width); return <ui.Raster key="heat" columns={r.columns} rows={r.rows} cells={r.cells} /> })()
    : <ui.Svg source={heatSvg(hm, m)} alt={`${fmt(hm.yearTotal)} tokens in the last year`} isInteractive />

  const months = (s.tokens.monthly[key] || []).slice(-6)
  const maxMonth = Math.max(1, ...months.map(x => x[m]))
  const viewOptions = [{ value: 'all', label: 'Whole team' }, ...s.accounts.map(a => ({ value: String(a.number), label: a.label }))]

  return (
    <Box flexDirection="column" gap={1}>
      {alertsView($, ui, s)}
      <Box flexDirection="column">{lanes}<Text dimColor>Life bars: all of Claude on each account, from Anthropic</Text></Box>
      <Box flexDirection="column">
        <Box flexDirection="row" flexWrap="wrap" gap={1} alignItems="center">
          <Text bold>MATCH HISTORY · {m === 'cost' ? money(hm.yearCost) : fmt(m === 'output' ? hm.cells.reduce((n, c) => n + c.output, 0) : hm.yearTotal)} {m === 'cost' ? 'purse' : m === 'output' ? 'output tokens' : 'tokens'} in the last year</Text>
          {(['total', 'output', 'cost'] as Metric[]).map(x => (
            <Button key={`m-${x}`} plain={x === m ? undefined : true} label={x === 'total' ? 'Tokens' : x === 'output' ? 'Output' : 'Purse'}
              onPress={() => update($, metric, () => x)} />
          ))}
          {s.accounts.length > 1 && e.surface !== 'mobile' && (
            <ui.Select key="view" options={viewOptions} value={key} onSelect={(val: string) => update($, view, () => val)} />
          )}
        </Box>
        {heat}
        <Text dimColor>Claude Code on this computer only · cold → hot · show streak {hm.streak} (best {hm.longestStreak}) · {hm.activeDays} nights in the ring{hm.busiest ? ` · main event ${hm.busiest.date} (${fmt(hm.busiest.total)})` : ''}</Text>
      </Box>
      <Text><Text bold color="warning">SCORE {String(Math.round(t.lifetime.total)).padStart(12, '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</Text> · tonight <Text bold>{fmt(t.today.total)}</Text> ({money(t.today.cost)}) · this month <Text bold>{fmt(t.month.total)}</Text> ({money(t.month.cost)}) · purse {money(t.lifetime.cost)} · last hour {fmt(s.tokens.burnPerHour)}</Text>
      <Text dimColor>{scoreNote(t.lifetime)}</Text>
      <Box flexDirection="column">
        <Text bold>HIGH SCORES · MONTHS</Text>
        {months.map(x => <Text key={`mo-${x.month}`}>{x.month}  {bar((x[m] / maxMonth) * 100, 24)}  {m === 'cost' ? money(x.cost) : fmt(x[m])}</Text>)}
      </Box>
      <Box flexDirection="column">
        <Text bold>MOVESET · MODELS, 30 DAYS</Text>
        {s.tokens.models.slice(0, 4).map(x => <Text key={`md-${x.model}`}>{x.model.padEnd(20)} {fmt(x.total).padStart(7)}  out {fmt(x.output).padStart(7)}  {money(x.cost)}</Text>)}
      </Box>
      {s.sessions.length > 0 && (
        <Box flexDirection="column">
          <Text bold>MATCHES IN PROGRESS</Text>
          {s.sessions.slice(0, 6).map(x => {
            const who = s.accounts.find(a => String(a.number) === x.account)?.label || x.account || '?'
            return <Text key={`ss-${x.pid}`} dimColor>{who} · {x.cwd.split(/[\\/]/).slice(-2).join('/')} · {x.entrypoint || ''}{x.status ? ` · ${x.status}` : ''}</Text>
          })}
        </Box>
      )}
    </Box>
  )
}

async function setupView($: any, ui: any, s: Snapshot) {
  const { Box, Text, Button } = ui
  const pending = await read($, confirm)
  return (
    <Box flexDirection="column" gap={1}>
      <Box flexDirection="column">
        <Text bold>PRE-MATCH CHECKLIST</Text>
        {s.setup.map(c => <Text key={`chk-${c.id}`} color={c.ok ? 'success' : 'warning'}>{c.ok ? '■' : '□'} {c.label}</Text>)}
      </Box>
      <Box flexDirection="column">
        <Text bold>SIGN A PARTNER</Text>
        <Box flexDirection="row" flexWrap="wrap" gap={1}>
          <Button key="save-current" variant="primary" label="Sign current login" onPress={() => act($, 'Signing', ['sign', '--json'])} />
          <Button key="login" label="Bring in a new partner (/login)" onPress={async () => {
            await update($, note, () => 'After /login, press "Sign current login".')
            try { await $.command.run({ command: 'login', args: '' }) } catch { $.ui.toast('Type /login in the prompt, then press "Sign current login".') }
          }} />
        </Box>
        <Text dimColor>Your current partner is signed first, so nobody's lost when you log in to another account.</Text>
        {ui.Input && (
          <ui.Input key="token" label="Or sign by contract: a token (claude setup-token) or API key" placeholder="sk-ant-…" submitLabel="Sign"
            onSubmit={(val: string) => { if (val.trim()) void act($, 'Signing by contract', ['sign', '--contract', '--json'], val.trim() + '\n') }} />
        )}
      </Box>
      <Box flexDirection="column">
        <Text bold>THE ROSTER</Text>
        {s.accounts.map(a => (
          <Box key={`mg-${a.number}`} flexDirection="row" flexWrap="wrap" gap={1} alignItems="center">
            <Text>{String(a.number).padStart(2)} {a.email}{a.alias ? ` "${a.alias}"` : ''}{a.disabled ? ' · benched' : ''}</Text>
            <Button key={`en-${a.number}`} plain label={a.disabled ? 'Unbench' : 'Bench'}
              onPress={() => act($, a.disabled ? 'Unbenching' : 'Benching', [a.disabled ? 'unbench' : 'bench', String(a.number), '--json'])} />
            <Button key={`rm-${a.number}`} plain label={pending === String(a.number) ? 'Sure? Release' : 'Release'}
              onPress={async () => {
                if (pending === String(a.number)) {
                  await update($, confirm, () => null)
                  await act($, 'Releasing', ['release', String(a.number), '--json'])
                } else await update($, confirm, () => String(a.number))
              }} />
            {ui.Input && (
              <ui.Input key={`al-${a.number}`} placeholder="ring name" value={a.alias || ''} submitLabel="Set ring name"
                onSubmit={(val: string) => act($, 'Saving ring name', ['ring-name', String(a.number), ...(val.trim() ? [val.trim()] : []), '--json'])} />
            )}
          </Box>
        ))}
      </Box>
    </Box>
  )
}

function autoView($: any, ui: any, s: Snapshot) {
  const { Box, Text, Button } = ui
  const A = s.auto
  const set = (k: string, val: string) => act($, 'Saving', ['blind-tag', 'set', k, val, '--json'])
  const label = (n?: number) => s.accounts.find(a => a.number === n)?.label || (n ?? '?')
  return (
    <Box flexDirection="column" gap={1}>
      <Box flexDirection="row" flexWrap="wrap" gap={1} alignItems="center">
        <Text bold>BLIND TAG is {A.enabled ? 'ON' : 'OFF'}</Text>
        <Button key="auto-toggle" variant="primary" label={A.enabled ? 'Turn off' : 'Turn on'}
          onPress={() => act($, A.enabled ? 'Turning off' : 'Turning on', ['blind-tag', A.enabled ? 'off' : 'on', '--json'])} />
        <Button key="auto-preview" label="What would the corner do?" onPress={() => act($, 'Asking the corner', ['blind-tag', 'preview', '--json'])} />
      </Box>
      <Text dimColor>{!A.enabled ? 'Off: TAG ME asks you before every tag.'
        : A.serviceInstalled ? 'On, and the corner man keeps watch even with Claude Code closed.'
        : 'On while Claude Code is open: partners tag out before they are worn down.'}</Text>
      <Button key="auto-svc" label={A.serviceInstalled ? 'Send the corner man home' : 'Corner man: keep watch when Claude Code is closed'}
        onPress={() => act($, 'Calling the corner man', ['corner-man', A.serviceInstalled ? 'uninstall' : 'install', '--json'])} />
      <Box flexDirection="column">
        <Text bold>RULES OF THE MATCH</Text>
        {ui.Select && (
          <ui.Select key="auto-strategy" label="Tag in the partner with" value={String(A.settings.strategy ?? 'best')}
            options={[{ value: 'best', label: 'most stamina left' }, { value: 'consume-first', label: 'soonest weekly reset' }]}
            onSelect={(val: string) => set('strategy', val)} />
        )}
        {ui.Select && (
          <ui.Select key="auto-threshold" label="Tag-out point" value={String(Math.round(Number(A.settings.threshold ?? 90)))}
            options={['70', '75', '80', '85', '90', '95', '98'].map(x => ({ value: x, label: `${x}%` }))}
            onSelect={(val: string) => set('threshold', val)} />
        )}
        {ui.Select && (
          <ui.Select key="auto-cooldown" label="Breather between tags" value={String(Math.round(Number(A.settings.cooldownSeconds ?? 300)))}
            options={['60', '300', '600', '1800'].map(x => ({ value: x, label: `${Number(x) / 60} min` }))}
            onSelect={(val: string) => set('cooldownSeconds', val)} />
        )}
      </Box>
      <Box flexDirection="column">
        <Text bold>RECENT BLIND TAGS</Text>
        {A.recent.length === 0 && <Text dimColor>No blind tags yet.</Text>}
        {A.recent.slice(-8).reverse().map((ev, i) => (
          <Text key={`ev-${i}`} dimColor>{ev.ts.replace('T', ' ').slice(0, 16)}  {ev.event === 'switch' ? `${label(ev.from?.number)} tags ${label(ev.to?.number)} (${ev.trigger})` : ev.event}</Text>
        ))}
      </Box>
    </Box>
  )
}

/** Markdown fallback: readable on any surface, even one that draws no plugin UI. */
export function summary(s: Snapshot): string {
  const pct = (a: Account) => {
    const u = usageOf(a)
    return [u.fiveHour ? `${Math.round(u.fiveHour.pct)}%` : '—', u.sevenDay ? `${Math.round(u.sevenDay.pct)}%` : '—']
  }
  const t = s.tokens.totals.all
  const lines = [
    `**TAG TEAM WRESTLING** · in the ring: **${s.active.label || 'nobody'}**${s.active.managed ? '' : ' (not signed)'}`,
    '',
    '| # | Partner | Stamina (5h) | Endurance (7d) | Tonight | Month | |',
    '|---|---|---|---|---|---|---|',
    ...s.accounts.map(a => {
      const [five, seven] = pct(a)
      return `| ${a.number} | ${a.label} | ${five} | ${seven} | ${fmt(a.tokens.today.total)} | ${fmt(a.tokens.month.total)} | ${a.active ? '**IN THE RING**' : a.nearLimit ? 'worn down' : 'on the apron'} |`
    }),
    '',
    t ? `Tokens: tonight **${fmt(t.today.total)}** (${money(t.today.cost)}) · this month **${fmt(t.month.total)}** (${money(t.month.cost)}) · career **${fmt(t.lifetime.total)}** (purse ${money(t.lifetime.cost)})\n\n_${scoreNote(t.lifetime)}. The Stamina and Endurance columns count all of Claude on each account._` : '',
    ...s.alerts.map(a => `\n${a.kind === 'near-limit' ? `**${a.ko ? 'DOWN FOR THE COUNT' : 'REACH FOR THE TAG'}!** ` : '⚠ '}${a.message}.${a.suggest ? ` **TAG ME:** run \`/tag-out\` to tag in ${a.suggest.label} (${Math.round(a.suggest.pct)}% used).` : ''}`),
    '',
    'Tag in: `/tag-in <number|ring name|best>` · hot tag: `/tag-out` · ring card: `/roster` · blind tag: `/blind-tag on`',
  ]
  return lines.join('\n')
}

/** The whole dashboard: drawn in the pane, or inline where the surface places no panes. */
async function dashboard($: any, e: any) {
  const ui = $.ui.resolve(e) as any
  const { Box, Text, Button } = ui
  const s = await read($, snap)
  const err = await read($, error)
  const working = await read($, busy)
  const msg = await read($, note)
  const current = await read($, tab)
  const width = Math.max(40, (e.props as any).bodyColumns || e.viewport?.columns || 80)

  const header = (
    <Box flexDirection="row" flexWrap="wrap" gap={1} alignItems="center">
      {s?.mascot && (e.surface === 'terminal'
        ? (() => { const r = mascotRaster(s.mascot); return <ui.Raster key="mascot" columns={r.columns} rows={r.rows} cells={r.cells} /> })()
        : <ui.Svg source={mascotSvg(s.mascot, 2)} alt="Tag Team Wrestling mascot: two partners slapping hands" />)}
      <Box flexDirection="column">
        <Text bold color="warning">TAG TEAM WRESTLING</Text>
        <Text dimColor>{s ? `in the ring: ${s.active.label || 'nobody'}${s.active.managed ? '' : ' (not signed)'}` : 'lacing up…'}</Text>
      </Box>
      {(['overview', 'setup', 'auto'] as Tab[]).map(t => (
        <Button key={`tab-${t}`} plain={t === current ? undefined : true} variant={t === current ? 'primary' : undefined}
          label={t === 'overview' ? 'Ring' : t === 'setup' ? 'Roster' : 'Blind tag'}
          onPress={() => update($, tab, () => t)} />
      ))}
      <Button key="refresh" label="Refresh" onPress={() => refresh($)} />
    </Box>
  )
  const status = (
    <Box flexDirection="column">
      {err && <Text color="error">{err}</Text>}
      {working && <Text dimColor>{working}…</Text>}
      {msg && !working && <Text dimColor>{msg}</Text>}
    </Box>
  )
  if (!s) return <Box flexDirection="column" gap={1}>{header}{status}{!err && <Text dimColor>Lacing up: reading the match history…</Text>}</Box>

  const body = current === 'setup' ? await setupView($, ui, s) : current === 'auto' ? autoView($, ui, s) : await overview($, ui, e, s, width)
  return <Box flexDirection="column" gap={1}>{header}{status}{body}</Box>
}

export const register: Register = (on, options) => {
  BIN = String(options.tagteamPath || 'tagteam')
  RESOLVED = null
  REFRESH_MS = Math.max(30, Number(options.refreshSeconds) || 60) * 1000

  on('session.start', async ($, e, next) => {
    // One refused name (a clash with another plugin) must not stop the rest.
    await Promise.allSettled([
      $.command.register({ name: 'tag-team', description: 'Open the ring: your Claude accounts as a tag team, stamina, match history' }),
      $.command.register({ name: 'tag-in', description: 'Tag a partner into the ring (switch Claude account)', argumentHint: '[best|N|ring name]' }),
      $.command.register({ name: 'tag-out', description: 'Hot tag: hand off to the partner with the most stamina left' }),
      $.command.register({ name: 'roster', description: 'Ring card: roster, stamina and match history in the chat' }),
      $.command.register({ name: 'blind-tag', description: 'Automatic tagging before a partner is worn down', argumentHint: '[on|off|preview|status]' }),
    ])
    void refresh($)
    $.clock.every(REFRESH_MS, () => { void refresh($) })
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if ((await $.clock.now()) - lastRefresh > 20_000) void refresh($)
    return next(e)
  })

  on('command.run', { command: 'tag-team' }, async $ => {
    await open($)
    await refresh($)
    // Markdown fallback for surfaces that draw no plugin UI; CommandOutput below swaps in the ring.
    const s = await read($, snap)
    return { text: s ? summary(s) : `Tag Team: ${(await read($, error)) || 'no match history yet'}` }
  })

  on('command.run', { command: 'tag-in' }, async ($, e) => {
    const target = e.args.trim() || 'best'
    try {
      const r = await tagteam($, ['tag-in', target, '--json'])
      void refresh($)
      return { text: r.message || 'TAG!' }
    } catch (err) {
      return { text: `Missed the tag: ${(err as Error).message}` }
    }
  })

  on('command.run', { command: 'tag-out' }, async $ => {
    try {
      const r = await tagteam($, ['tag-out', '--json'])
      void refresh($)
      return { text: r.message || 'TAG!' }
    } catch (err) {
      return { text: `Missed the tag: ${(err as Error).message}` }
    }
  })

  on('command.run', { command: 'roster' }, async $ => {
    try {
      const r = await tagteam($, ['ring-card'])
      return { text: '```\n' + (r.message || '') + '\n```' }
    } catch (err) {
      return { text: `Tag Team: ${(err as Error).message}` }
    }
  })

  on('command.run', { command: 'blind-tag' }, async ($, e) => {
    const verb = (e.args.trim() || 'status').split(/\s+/)[0] ?? 'status'
    if (!['on', 'off', 'preview', 'status'].includes(verb)) return { text: 'Usage: /blind-tag on|off|preview|status' }
    try {
      const r = await tagteam($, ['blind-tag', verb, '--json'])
      void refresh($)
      return { text: r.message || (r.enabled ? 'Blind tag is on.' : 'Blind tag is off.') }
    } catch (err) {
      return { text: `Tag Team: ${(err as Error).message}` }
    }
  })

  // The band above the prompt appears only when the active account nears its limit.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const s = await read($, snap)
    const near = s?.alerts.find(x => x.kind === 'near-limit')
    const hiddenKey = near ? `${near.account}:${Math.floor((near.pct ?? 0) / 5)}` : null
    if (!s || !near || (await read($, bandHidden)) === hiddenKey || s.auto.enabled) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e) as any
    const working = await read($, busy)
    return (
      <Box flexDirection="row" flexWrap="wrap" gap={1} alignItems="center">
        <Text color="error" bold>{near.ko ? 'DOWN FOR THE COUNT!' : 'REACH FOR THE TAG!'}</Text>
        <Text>{near.message}.</Text>
        {near.suggest && (
          <Button key="to" variant="primary" label={`TAG ME > ${near.suggest.label} (${Math.round(near.suggest.pct)}%)`}
            onPress={() => act($, 'TAG!', ['tag-in', String(near.suggest!.number), '--json'])} />
        )}
        {!near.suggest && <Text dimColor>Nobody on the apron has stamina left.</Text>}
        <Button key="dash" label="Ring" onPress={() => open($)} />
        <Button key="hide" label="Hide" role="dismiss" onPress={() => update($, bandHidden, () => hiddenKey)} />
        {working && <Text dimColor>{working}…</Text>}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => dashboard($, e))

  // Editors place no panes (and headless sessions report every pane placed), so they get the ring inline.
  on('ui.render', { component: 'CommandOutput', props: { command: 'tag-team' } }, async ($, e, next) =>
    e.surface === 'terminal' ? next(e) : dashboard($, e))
}
