/** Relays URL changes and the keyboard shortcut to the page's control. It makes no network request. */
chrome.tabs.onUpdated.addListener((id, info, tab) => {
  if (info.url || info.status === 'complete') void chrome.tabs.sendMessage(id, { type: 'url', url: tab.url }).catch(() => undefined)
})

chrome.commands.onCommand.addListener((command) => {
  if (command !== 'capture') return
  void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
    if (tab?.id !== undefined) void chrome.tabs.sendMessage(tab.id, { type: 'command' }).catch(() => undefined)
  })
})
