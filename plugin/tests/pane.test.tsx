import { describe, expect, mock, test } from 'claude-code/testing'

import { SNAP } from './fixture'

const ran: string[][] = []

const runs: any[] = []

function fakeTagteam(on: any, notifyFails = false) {
  const clock = mock.clock(on)
  // A planted ./tagteam in the project and a relative PATH entry must never be picked.
  mock.env(on, { PATH: '.:/opt/tt/bin:/usr/bin', HOME: '/home/u' })
  on('fs.exists', ($: any, e: any) => ({ value: e.path === '/opt/tt/bin/tagteam' || e.path === './tagteam' || e.path === './/tagteam' }))
  on('process.run', ($: any, e: any) => {
    ran.push([...e.argv])
    runs.push(e)
    if (notifyFails && e.argv[1] === 'notify') return { value: { exitCode: 1, stdout: '{"ok": false, "error": "no desktop notifier found"}', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    const out = e.argv[1] === 'state' ? JSON.stringify(SNAP) : JSON.stringify({ ok: true, switched: true, message: 'TAG! acct1 is in the ring.' })
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  return clock
}

const PANE_PROPS = {
  title: 'Tag Team Wrestling', isFocused: false, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 60 }, view: {},
}

describe('tag-team ring', () => {
  test('shows THIS MATCH for the session the pane runs in', async ($: any, on: any) => {
    fakeTagteam(on)
    on('session.id', () => ({ value: 'sess-1' }))
    await $.command.run({ command: 'tag-team', args: '' })
    const ui = await $.ui.mount({ plugin: 'tag-team', surface: 'terminal', component: 'Pane', requestId: 'tag-team', props: PANE_PROPS })
    expect(await ui.find({ text: /THIS MATCH/ })).toBeDefined()
    expect(await ui.find({ text: /Fix the login form/ })).toBeDefined()
    await ui.unmount()
  })

  test('draws accounts, heatmap and switches on press, on every surface', async ($: any, on: any) => {
    fakeTagteam(on)
    await $.command.run({ command: 'tag-team', args: '' })
    for (const surface of ['terminal', 'vscode', 'desktop'] as const) {
      const ui = await $.ui.mount({ plugin: 'tag-team', surface, component: 'Pane', requestId: 'tag-team', props: PANE_PROPS })
      expect(await ui.find({ text: /MATCH HISTORY/ })).toBeDefined()
      expect(await ui.find({ key: 'sw-1' })).toBeDefined()
      expect(await ui.find({ type: surface === 'terminal' ? 'Raster' : 'Svg' })).toBeDefined()
      await ui.press({ key: 'sw-1' })
      expect(ran.some(a => a[1] === 'tag-in' && a[2] === '1')).toBe(true)
      await ui.unmount()
    }
  })

  test('TAG ME band offers the tag when the partner in the ring is worn down', async ($: any, on: any) => {
    fakeTagteam(on)
    await $.command.run({ command: 'tag-team', args: '' })
    const band = await $.ui.mount({
      plugin: 'tag-team', surface: 'terminal', component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 100, scroll: { offset: 0, bodyRows: 10 }, view: {} },
    })
    expect(await band.find({ key: 'to' })).toBeDefined()
  })

  test('editors that place no panes get the ring inline under /tag-team', async ($: any, on: any) => {
    fakeTagteam(on)
    await $.command.run({ command: 'tag-team', args: '' })
    const row = await $.ui.mount({
      plugin: 'tag-team', surface: 'vscode', component: 'CommandOutput',
      props: { command: 'tag-team', args: '', text: 'summary', isErrored: false },
    })
    expect(await row.find({ text: /MATCH HISTORY/ })).toBeDefined()
    expect(await row.find({ type: 'Svg' })).toBeDefined()
    await row.press({ key: 'sw-1' })
    expect(ran.some(a => a[1] === 'tag-in' && a[2] === '1')).toBe(true)
  })

  test('the reply text alone is a readable summary', async ($: any, on: any) => {
    fakeTagteam(on)
    const res = await $.command.run({ command: 'tag-team', args: '' })
    expect(res.text).toMatch(/\| 1 \| acct1 \|/)
    expect(res.text).toMatch(/tag-out/)
  })

  test('runs tagteam by absolute path from home, never from the project folder', async ($: any, on: any) => {
    fakeTagteam(on)
    await $.command.run({ command: 'tag-team', args: '' })
    const last = runs[runs.length - 1]
    expect(last.argv[0]).toBe('/opt/tt/bin/tagteam')
    expect(last.init.cwd).toBe('/home/u')
  })
})

describe('notify me', () => {
  // Desktop notifications go out as `tagteam notify MESSAGE --kind K [--title T]`.
  const sent = () => ran.filter(a => a[1] === 'notify').map(a => a[2])
  const kinds = () => ran.filter(a => a[1] === 'notify').map(a => a[a.indexOf('--kind') + 1])
  const asking = (on: any) => {
    const clock = fakeTagteam(on)
    on('tool.check', () => ({ decision: 'ask' }))
    return clock
  }

  test('pings when Claude puts a question to the person', async ($: any, on: any) => {
    ran.length = 0
    const clock = asking(on)
    await $.tool.call({ tool: 'AskUserQuestion', questions: [] }).catch(() => {})
    await clock.settle() // the ping runs on a timer, after the permission check returns
    expect(sent()).toContain('Claude has a question for you in the ring.')
    expect(kinds()).toEqual(['question'])
  })

  test('an approval pings exactly once, from the dialog', async ($: any, on: any) => {
    ran.length = 0
    const clock = asking(on)
    on('classic.PermissionRequest', () => ({ value: {} }))
    await $.tool.call({ tool: 'Bash', command: 'ls' }).catch(() => {})
    await clock.settle()
    expect(sent()).toEqual(['Claude wants to use Bash. Approve or deny in the session.'])
    expect(kinds()).toEqual(['approval'])
  })

  for (const mode of ['default', 'acceptEdits', 'plan', 'auto']) {
    test(`pings when the approval dialog really opens (${mode})`, async ($: any, on: any) => {
      ran.length = 0
      const clock = fakeTagteam(on)
      on('classic.PermissionRequest', () => ({ value: {} })) // the dialog itself, beneath the plugin
      await $.classic.PermissionRequest({ tool_name: 'Bash', tool_input: { command: 'ls' }, permission_mode: mode })
      await clock.settle()
      expect(sent()).toEqual(['Claude wants to use Bash. Approve or deny in the session.'])
      expect(kinds()).toEqual(['approval'])
    })
  }

  test("a subagent's dialog doesn't ping twice for the same session", async ($: any, on: any) => {
    ran.length = 0
    const clock = fakeTagteam(on)
    on('classic.PermissionRequest', () => ({ value: {} }))
    await $.classic.PermissionRequest({ tool_name: 'Bash', tool_input: {}, permission_mode: 'default', agent_id: 'a1' })
    await clock.settle()
    expect(sent()).toEqual([])
  })

  test('Claude can send its own notification', async ($: any, on: any) => {
    ran.length = 0
    fakeTagteam(on)
    const r = await $.tool.call({ tool: 'mcp__tag-team__notify', message: 'Tests failed on main', kind: 'error' })
    expect(sent()).toContain('Tests failed on main')
    expect(kinds()).toEqual(['error'])
    expect(r.text).toBe('Notification sent.')
  })

  test('falls back to Claude Code\'s notification when the CLI cannot notify', async ($: any, on: any) => {
    const via: string[] = []
    const titles: string[] = []
    fakeTagteam(on, true)
    on('ui.notify', ($: any, e: any) => { via.push(e.text); titles.push(e.title); return { value: { isSent: true, channel: 'terminal' } } })
    const r = await $.tool.call({ tool: 'mcp__tag-team__notify', message: 'Deploy done' })
    expect(via).toEqual(['Deploy done'])
    expect(titles).toEqual(['🔔 Ringside update'])
    expect(r.text).toBe('Notification sent.')
  })

  test('switched off in the Notify tab: no fallback, and Claude is told', async ($: any, on: any) => {
    const via: string[] = []
    const clock = mock.clock(on)
    mock.env(on, { PATH: '/opt/tt/bin:/usr/bin', HOME: '/home/u' })
    on('fs.exists', ($: any, e: any) => ({ value: e.path === '/opt/tt/bin/tagteam' }))
    on('process.run', ($: any, e: any) => ({ value: { exitCode: e.argv[1] === 'notify' ? 1 : 0, stderr: '', isStdoutTruncated: false, isStderrTruncated: false,
      stdout: e.argv[1] === 'notify' ? '{"ok": false, "off": true, "error": "notifications are off (tagteam notifications on)"}' : JSON.stringify(SNAP) } }))
    on('ui.notify', ($: any, e: any) => { via.push(e.text); return { value: { isSent: true, channel: 'terminal' } } })
    const r = await $.tool.call({ tool: 'mcp__tag-team__notify', message: 'Deploy done' })
    await clock.settle()
    expect(via).toEqual([])
    expect(r.isError).toBe(true)
    expect(r.text).toMatch(/Notifications are off/)
  })

  test('tells Claude when neither path can notify', async ($: any, on: any) => {
    fakeTagteam(on, true)
    on('ui.notify', () => ({ value: { isSent: false, reason: 'no-channel' } }))
    const r = await $.tool.call({ tool: 'mcp__tag-team__notify', message: 'Deploy done' })
    expect(r.isError).toBe(true)
    expect(r.text).toMatch(/Not sent/)
  })

  test('stays quiet with notifyMe off', { options: { notifyMe: false } }, async ($: any, on: any) => {
    ran.length = 0
    const clock = asking(on)
    await $.tool.call({ tool: 'Bash', command: 'ls' }).catch(() => {})
    await clock.settle()
    expect(sent()).toEqual([])
  })
})
