// Tag Team Wrestling for VS Code / VSCodium: [IN] / TAG ME status bar and the ring panel, via the tagteam CLI.
const vscode = require('vscode')
const cp = require('child_process')
const fs = require('fs')
const path = require('path')
const os = require('os')

let snap = null
let panel = null
let item = null
let timer = null
let alerted = null
let inflight = null

// User settings only: a workspace (e.g. a cloned repo's .vscode/settings.json) must never pick the executable we run.
const setting = key => {
  const v = vscode.workspace.getConfiguration('tagTeam').inspect(key)
  const old = vscode.workspace.getConfiguration('swapMe').inspect(key === 'tagteamPath' ? 'swapmePath' : key)
  return v?.globalValue ?? old?.globalValue ?? v?.defaultValue
}
const fmt = n => { n = Number(n) || 0; for (const [u, s] of [['B', 1e9], ['M', 1e6], ['K', 1e3]]) if (Math.abs(n) >= s) return (n / s).toFixed(1) + u; return String(Math.round(n)) }
const usageOf = a => a.usage || a.lastGoodUsage || {}
const pct = w => (w ? `${Math.round(w.pct)}%` : '-')
const pips = w => { const left = Math.round(Math.max(0, 100 - (w?.pct ?? 0)) / 20); return '▮'.repeat(left) + '▯'.repeat(5 - left) }

// Absolute path from PATH only: Windows would otherwise try the workspace folder first.
function resolveBin(name) {
  if (path.isAbsolute(name)) return name
  const exts = process.platform === 'win32' ? (process.env.PATHEXT || '.EXE;.CMD;.BAT').split(';') : ['']
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    if (!dir || !path.isAbsolute(dir)) continue
    for (const ext of exts) {
      const file = path.join(dir, name + ext.toLowerCase())
      try { if (fs.statSync(file).isFile()) return file } catch { /* keep looking */ }
    }
  }
  return null
}

function tagteam(args, stdin) {
  return new Promise((resolve, reject) => {
    let name = setting('tagteamPath') || 'tagteam'
    if (name === 'swapme') name = 'tagteam'
    const bin = resolveBin(name)
    if (!bin) return reject(new Error(`Can't find "${name}" on PATH. Install Tag Team, or set tagTeam.tagteamPath in Settings.`))
    const child = cp.execFile(bin, args, { cwd: os.homedir(), env: { ...process.env, NO_COLOR: '1' }, timeout: 120000, maxBuffer: 64 * 1024 * 1024, windowsHide: true, shell: false }, (err, stdout, stderr) => {
      const text = String(stdout || '').trim()
      let data = null
      try { data = text ? JSON.parse(text.split('\n').pop()) : null } catch { /* plain text */ }
      if (err && err.code === 'ENOENT') return reject(new Error(`Can't find "${bin}". Install Tag Team, or set tagTeam.tagteamPath in Settings.`))
      if (err || (data && data.ok === false)) return reject(new Error((data && data.error) || String(stderr || text || err.message).trim()))
      resolve(data ?? { message: text })
    })
    if (stdin) child.stdin.end(stdin)
  })
}

async function refresh() {
  if (inflight) return inflight
  inflight = (async () => {
    try {
      snap = await tagteam(['state'])
      render()
      if (panel) panel.webview.postMessage({ type: 'state' })
      if (snap.auto.enabled && !snap.auto.serviceInstalled) blindTag()
    } catch (e) {
      item.text = '$(person) Tag Team'
      item.tooltip = e.message
      item.command = 'tagTeam.open'
      item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground')
    } finally {
      inflight = null
    }
  })()
  return inflight
}

function render() {
  const a = snap.accounts.find(x => x.active)
  const u = a ? usageOf(a) : {}
  const near = snap.alerts.find(x => x.kind === 'near-limit')
  if (near && !snap.auto.enabled) {
    // TAG ME: one click hands off to the freshest partner, no dialog.
    item.text = `$(megaphone) TAG ME · ${snap.active.label} ${pct(u.fiveHour)}`
    item.command = 'tagTeam.tagOut'
    item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground')
  } else {
    item.text = `$(person) [IN] ${snap.active.label || 'nobody'}${u.fiveHour ? ` ${pips(u.fiveHour)} ${pct(u.fiveHour)}` : ''}${snap.auto.enabled ? ' $(sync)' : ''}`
    item.command = 'tagTeam.open'
    item.backgroundColor = near ? new vscode.ThemeColor('statusBarItem.warningBackground') : undefined
  }
  const md = new vscode.MarkdownString(undefined, true)
  md.isTrusted = { enabledCommands: ['tagTeam.open', 'tagTeam.tagIn', 'tagTeam.tagOut'] }
  md.appendMarkdown(`**TAG TEAM WRESTLING** · in the ring: **${snap.active.label || 'nobody'}**\n\n| Partner | Stamina 5h | Endurance 7d | Tonight |\n|---|---|---|---|\n`)
  for (const x of snap.accounts) {
    const xu = usageOf(x)
    md.appendMarkdown(`| ${x.active ? '▶ ' : ''}${x.label} | ${pct(xu.fiveHour)} | ${pct(xu.sevenDay)} | ${fmt(x.tokens.today.total)} |\n`)
  }
  const t = snap.tokens.totals.all
  md.appendMarkdown(`\nTonight ${fmt(t.today.total)} · this month ${fmt(t.month.total)} · career ${fmt(t.lifetime.total)}\n\n` +
    `[$(home) Open the ring](command:tagTeam.open) · [$(person-add) Tag in…](command:tagTeam.tagIn) · [$(megaphone) Hot tag](command:tagTeam.tagOut)`)
  item.tooltip = md

  // Prompt once per 5% step and again at 100% (down for the count).
  const key = near ? `${near.account}:${near.ko ? 'ko' : Math.floor((near.pct || 0) / 5)}` : null
  if (near && key !== alerted && !snap.auto.enabled) promptTagMe(near)
  alerted = key
}

async function promptTagMe(near) {
  const actions = [...(near.suggest ? [`TAG ME > ${near.suggest.label}`] : []), 'Hot tag: best', 'Open the ring']
  const head = near.ko ? 'DOWN FOR THE COUNT!' : 'REACH FOR THE TAG!'
  const fresh = near.suggest ? ` ${near.suggest.label} is fresh (${Math.round(near.suggest.pct)}% used).` : ' Nobody on the apron has stamina left.'
  const pick = await vscode.window.showWarningMessage(`${head} ${near.message}.${fresh}`, ...actions)
  if (!pick) return
  if (pick === 'Open the ring') return openRing()
  await doTag(pick === 'Hot tag: best' ? ['tag-out', '--json'] : ['tag-in', String(near.suggest.number), '--json'])
}

async function doTag(args) {
  try {
    const r = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Tag Team: reaching for the tag…' }, () => tagteam(args))
    vscode.window.showInformationMessage(r.message || 'TAG!')
    if (panel) panel.webview.postMessage({ type: 'tagged' })
  } catch (e) {
    vscode.window.showErrorMessage(`Missed the tag: ${e.message}`)
  }
  await refresh()
}

async function quickTagIn() {
  if (!snap) await refresh()
  if (!snap) return
  const items = [
    { label: '$(megaphone) Hot tag', description: snap.best ? `${snap.best.label}, ${Math.round(snap.best.pct)}% used` : 'the partner with the most stamina', target: 'best' },
    ...snap.accounts.map(a => {
      const u = usageOf(a)
      return {
        label: `${a.active ? '$(person) [IN] ' : a.disabled ? '$(circle-slash) ' : '$(person-add) '}${a.label}`,
        description: `stamina ${pct(u.fiveHour)} · endurance ${pct(u.sevenDay)}${a.nearLimit ? ' · worn down' : ''}`,
        detail: `${a.email} · tonight ${fmt(a.tokens.today.total)} · month ${fmt(a.tokens.month.total)}${a.liveSessions ? ` · ${a.liveSessions} in progress` : ''}`,
        target: String(a.number),
        active: a.active,
      }
    }),
  ]
  const pick = await vscode.window.showQuickPick(items, { title: 'Tag a partner into the ring', placeHolder: 'Who should Claude Code use?', matchOnDetail: true })
  if (pick && !pick.active) await doTag(pick.target === 'best' ? ['tag-out', '--json'] : ['tag-in', pick.target, '--json'])
}

function ringHtml(context, webview) {
  const file = path.join(context.extensionPath, 'media', 'index.html')
  if (!fs.existsSync(file)) return '<p>Tag Team: the ring page is missing from this install.</p>'
  const csp = `default-src 'none'; img-src ${webview.cspSource} data:; style-src 'unsafe-inline'; font-src data:; script-src 'unsafe-inline';`
  return fs.readFileSync(file, 'utf8').replace('<head>', `<head><meta http-equiv="Content-Security-Policy" content="${csp}">`)
}

// The ring page's API, served from the CLI instead of the local web server.
function argsFor(p, b) {
  if (p.startsWith('/api/state')) return [['state']]
  if (p === '/api/switch') return [b.target ? ['tag-in', String(b.target), '--json'] : ['tag-out', '--json']]
  if (p === '/api/config') return [['tag-out-point', String(b.threshold), '--json']]
  if (p === '/api/account') {
    const n = String(b.number ?? '')
    switch (b.action) {
      case 'add': return [['sign', ...(b.alias ? ['--ring-name', b.alias] : []), '--json']]
      case 'add-token': return [['sign', '--contract', ...(b.email ? ['--email', b.email] : []), '--json'], `${b.token || ''}\n`]
      case 'alias': return [['ring-name', n, ...(b.alias ? [b.alias] : []), '--json']]
      case 'enable': return [['unbench', n, '--json']]
      case 'disable': return [['bench', n, '--json']]
      case 'remove': return [['release', n, '--json']]
    }
  }
  if (p === '/api/auto') {
    switch (b.action) {
      case 'toggle': return [['blind-tag', b.enabled ? 'on' : 'off', '--json']]
      case 'set': return [['blind-tag', 'set', b.key, String(b.value), '--json']]
      case 'preview': case 'once': return [['blind-tag', b.action, '--json']]
      case 'service-install': return [['corner-man', 'install', '--json']]
      case 'service-uninstall': return [['corner-man', 'uninstall', '--json']]
    }
  }
  throw new Error(`unknown action ${p}`)
}

function openRing(context) {
  context = context || openRing.context
  if (panel) return panel.reveal()
  panel = vscode.window.createWebviewPanel('tagTeam.ring', 'Tag Team Wrestling', { viewColumn: vscode.ViewColumn.Active, preserveFocus: false },
    { enableScripts: true, retainContextWhenHidden: true })
  panel.iconPath = vscode.Uri.file(path.join(context.extensionPath, 'media', 'icon.png'))
  panel.webview.html = ringHtml(context, panel.webview)
  panel.webview.onDidReceiveMessage(async m => {
    if (!m || !m.id) return
    try {
      if (m.path.startsWith('/api/state')) {
        if (m.path.includes('force=1') || !snap) await refresh()
        return panel.webview.postMessage({ id: m.id, result: snap })
      }
      const [args, stdin] = argsFor(m.path, m.body || {})
      const result = await tagteam(args, stdin)
      refresh()
      panel.webview.postMessage({ id: m.id, result })
    } catch (e) {
      panel.webview.postMessage({ id: m.id, error: e.message })
    }
  })
  panel.onDidDispose(() => { panel = null })
}

async function blindTag() {
  try {
    const r = await tagteam(['blind-tag', 'once', '--json'])
    if (String(r.message || '').startsWith('Blind tag!')) {
      vscode.window.showInformationMessage(`Tag Team: ${r.message}`)
      refresh()
    }
  } catch { /* next bell retries */ }
}

function schedule() {
  clearInterval(timer)
  timer = setInterval(refresh, Math.max(30, Number(setting('refreshSeconds')) || 60) * 1000)
}

function activate(context) {
  openRing.context = context
  item = vscode.window.createStatusBarItem('tagTeam.status', vscode.StatusBarAlignment.Right, 100)
  item.name = 'Tag Team Wrestling'
  item.text = '$(person) Tag Team'
  item.command = 'tagTeam.open'
  item.show()
  context.subscriptions.push(
    item,
    vscode.commands.registerCommand('tagTeam.open', () => openRing(context)),
    vscode.commands.registerCommand('tagTeam.tagIn', quickTagIn),
    vscode.commands.registerCommand('tagTeam.tagOut', () => doTag(['tag-out', '--json'])),
    vscode.commands.registerCommand('tagTeam.refresh', refresh),
    vscode.workspace.onDidChangeConfiguration(e => { if (e.affectsConfiguration('tagTeam') || e.affectsConfiguration('swapMe')) { schedule(); refresh() } }),
    { dispose: () => clearInterval(timer) },
  )
  schedule()
  refresh()
}

function deactivate() { clearInterval(timer) }

module.exports = { activate, deactivate, argsFor }
