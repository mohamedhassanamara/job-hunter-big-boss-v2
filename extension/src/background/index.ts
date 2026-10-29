/** Relays URL changes and the keyboard shortcut to the page's control, and makes the app calls for it. */
import { call, config, localOrigin } from './api'

chrome.tabs.onUpdated.addListener((id, info, tab) => {
  if (info.url || info.status === 'complete') void chrome.tabs.sendMessage(id, { type: 'url', url: tab.url }).catch(() => undefined)
})

chrome.commands.onCommand.addListener((command) => {
  if (command !== 'capture') return
  void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
    if (tab?.id !== undefined) void chrome.tabs.sendMessage(tab.id, { type: 'command' }).catch(() => undefined)
  })
})

// The pill and the options page ask the worker to talk to the app (the token stays here).
chrome.runtime.onMessage.addListener((raw, _sender, send) => {
  const msg = raw as { type?: string; path?: string; method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'; body?: unknown }
  if (msg.type === 'api' && msg.path) {
    void call(msg.path, msg.method ?? 'GET', msg.body).then(send)
    return true
  }
  if (msg.type === 'config') {
    void config().then((c) => send({ app: c.app, api: c.api, paired: !!c.token, localOk: !!localOrigin(c.api) }))
    return true
  }
  if (msg.type === 'options') {
    void chrome.runtime.openOptionsPage()
    send({})
    return true
  }
  return false
})
