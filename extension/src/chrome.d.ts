// Just the parts of the extension API this project uses (no @types/chrome dependency).
interface ChromeEvent<F> {
  addListener(cb: F): void
}
interface ChromeTab {
  id?: number
  url?: string
}
declare const chrome: {
  runtime: {
    id: string
    sendMessage(msg: unknown): Promise<unknown>
    openOptionsPage(): Promise<void>
    onMessage: ChromeEvent<(msg: unknown, sender: unknown, send: (r?: unknown) => void) => boolean | void>
  }
  tabs: {
    onUpdated: ChromeEvent<(id: number, info: { url?: string; status?: string }, tab: ChromeTab) => void>
    sendMessage(id: number, msg: unknown): Promise<unknown>
    query(q: Record<string, unknown>): Promise<ChromeTab[]>
  }
  commands: { onCommand: ChromeEvent<(command: string) => void> }
  storage: { local: { get(k: string): Promise<Record<string, unknown>>; set(o: Record<string, unknown>): Promise<void> } }
}
