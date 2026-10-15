import { describe, expect, mock, test } from 'claude-code/testing'

import { SNAP } from './fixture'

const ran: string[][] = []

const runs: any[] = []

function fakeTagteam(on: any) {
  mock.clock(on)
  // A planted ./tagteam in the project and a relative PATH entry must never be picked.
  mock.env(on, { PATH: '.:/opt/tt/bin:/usr/bin', HOME: '/home/u' })
  on('fs.exists', ($: any, e: any) => ({ value: e.path === '/opt/tt/bin/tagteam' || e.path === './tagteam' || e.path === './/tagteam' }))
  on('process.run', ($: any, e: any) => {
    ran.push([...e.argv])
    runs.push(e)
    const out = e.argv[1] === 'state' ? JSON.stringify(SNAP) : JSON.stringify({ ok: true, switched: true, message: 'TAG! acct1 is in the ring.' })
    return { value: { exitCode: 0, stdout: out, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
}

const PANE_PROPS = {
  title: 'Tag Team Wrestling', isFocused: false, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 60 }, view: {},
}

describe('tag-team ring', () => {
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
