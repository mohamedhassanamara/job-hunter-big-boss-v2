import { Archive, ArchiveRestore, Coins, ImagePlus, Package, Pencil, Plus, ShoppingBag, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ChestDialog } from '@/components/app/motivation/ChestDialog'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { absoluteDate } from '@/lib/format'
import { plural } from '@/lib/motivation'
import {
  motivationFile,
  useBuy,
  useChestHistory,
  useMotivation,
  useRedeem,
  useSaveShopItem,
  useShop,
  useTokens,
  useUploadImage,
} from '@/lib/queries/motivation'
import type { ShopItem } from '@/lib/types'
import { cn } from '@/lib/utils'

function ItemVisual({ item, className }: { item: Pick<ShopItem, 'emoji' | 'image_name' | 'name'>; className?: string }) {
  if (item.image_name) return <img src={motivationFile(item.image_name)} alt="" className={cn('object-cover', className)} />
  return <span className={cn('flex items-center justify-center bg-bg-subtle text-2xl', className)}>{item.emoji || '🎁'}</span>
}

function ItemDialog({ item, open, onOpenChange }: { item: ShopItem | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const save = useSaveShopItem()
  const upload = useUploadImage()
  const input = useRef<HTMLInputElement>(null)
  const [f, setF] = useState({ name: item?.name ?? '', price: String(item?.price ?? 5), emoji: item?.emoji ?? '', image_name: item?.image_name ?? null })
  const price = Number(f.price)
  const valid = f.name.trim() && Number.isInteger(price) && price >= 1 && price <= 10000
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={item ? 'Edit reward' : 'New reward'}>
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate(
              { id: item?.id, name: f.name, price, emoji: f.emoji || null, image_name: f.image_name },
              { onSuccess: () => (toast.success(item ? 'Reward saved' : 'Reward added'), onOpenChange(false)), onError: (err) => toast.error(err.message) },
            )
          }}
        >
          <h2 className="text-base font-semibold">{item ? 'Edit reward' : 'New reward'}</h2>
          <div className="flex gap-4">
            <button type="button" onClick={() => input.current?.click()} className="relative size-20 shrink-0 overflow-hidden rounded-lg border border-border" aria-label="Choose an image">
              <ItemVisual item={{ ...f, name: f.name }} className="size-full" />
              <span className="absolute right-1 bottom-1 rounded-sm bg-surface p-0.5 shadow-sm">
                <ImagePlus className="size-3.5" />
              </span>
            </button>
            <input
              ref={input}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) upload.mutate(file, { onSuccess: (r) => setF((x) => ({ ...x, image_name: r.name })), onError: (err) => toast.error(err.message) })
              }}
            />
            <div className="flex-1 space-y-3">
              <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Dinner at my favourite place" aria-label="Name" autoFocus />
              <div className="flex gap-2">
                <div className="relative w-32">
                  <Coins className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-tone-violet-dot" />
                  <Input value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} inputMode="numeric" aria-label="Price in tokens" aria-invalid={!valid && f.price !== ''} className="pl-8" />
                </div>
                <Input value={f.emoji} onChange={(e) => setF({ ...f, emoji: e.target.value })} placeholder="Emoji (optional)" aria-label="Emoji" className="w-36" maxLength={8} />
                {f.image_name && (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setF({ ...f, image_name: null })}>
                    <X />
                    Image
                  </Button>
                )}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="default" disabled={!valid || save.isPending || upload.isPending}>
              {item ? 'Save' : 'Add reward'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function BuyDialog({ item, balance, onClose }: { item: ShopItem | null; balance: number; onClose: () => void }) {
  const buy = useBuy()
  return (
    <Dialog open={item !== null} onOpenChange={(o) => !o && onClose()}>
      {item && (
        <DialogContent title={`Buy ${item.name}`} className="max-w-sm">
          <div className="space-y-4 p-5">
            <div className="flex items-center gap-3">
              <ItemVisual item={item} className="size-14 shrink-0 rounded-lg" />
              <div>
                <p className="text-sm font-medium">{item.name}</p>
                <p className="text-sm text-fg-muted">
                  {plural(item.price, 'token')} · balance after: {balance - item.price}
                </p>
              </div>
            </div>
            <p className="text-sm text-fg-muted">You earned it. Enjoy it, then tick it as redeemed in your purchases.</p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button
                variant="default"
                autoFocus
                disabled={buy.isPending}
                onClick={() => buy.mutate(item.id, { onSuccess: () => (toast.success(`${item.name}: bought`), onClose()), onError: (e) => toast.error(e.message) })}
              >
                Buy for {item.price}
              </Button>
            </div>
          </div>
        </DialogContent>
      )}
    </Dialog>
  )
}

/** The shop: rewards you set yourself, bought with the tokens from chests. */
export function ShopTab() {
  const shop = useShop()
  const summary = useMotivation()
  const chests = useChestHistory()
  const tokens = useTokens()
  const save = useSaveShopItem()
  const redeem = useRedeem()
  const [editing, setEditing] = useState<ShopItem | 'new' | null>(null)
  const [buying, setBuying] = useState<ShopItem | null>(null)
  const [opening, setOpening] = useState(false)
  const [showArchived, setShowArchived] = useState(false)

  if (shop.error) return <ErrorState error={shop.error} onRetry={() => shop.refetch()} />
  const balance = shop.data?.balance ?? 0
  const active = shop.data?.items.filter((i) => !i.archived) ?? []
  const archived = shop.data?.items.filter((i) => i.archived) ?? []
  const waiting = summary.data?.chests.available ?? 0
  const archive = (item: ShopItem, value: boolean) =>
    save.mutate(
      { id: item.id, archived: value },
      { onSuccess: () => toast(value ? `${item.name} archived` : `${item.name} is back`, { duration: 8000, action: { label: 'Undo', onClick: () => save.mutate({ id: item.id, archived: !value }) } }) },
    )

  return (
    <div className="mx-auto grid max-w-6xl gap-8 py-6 lg:grid-cols-[1fr_320px]" data-tour="motiv-shop">
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <h2 className="text-base font-semibold">Shop</h2>
            <p className="flex items-center gap-1.5 text-sm text-fg-muted">
              <Coins className="size-4 text-tone-violet-dot" />
              <span className="font-medium text-fg tabular-nums">{balance}</span> to spend
            </p>
          </div>
          {waiting > 0 && (
            <Button variant="secondary" onClick={() => setOpening(true)}>
              <Package />
              Open {waiting === 1 ? 'your chest' : `${waiting} chests`}
            </Button>
          )}
          <Button variant="default" onClick={() => setEditing('new')}>
            <Plus />
            New reward
          </Button>
        </div>
        {shop.isPending ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-44" />
            ))}
          </div>
        ) : active.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface">
            <EmptyState
              icon={ShoppingBag}
              title="Set your own rewards"
              description="A coffee out, a movie night, a day off: add treats with a token price. Chests pay tokens for every few applications."
              action={
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setEditing('new')}>
                    <Plus />
                    Add a reward
                  </Button>
                  <TourButton tour="motivation" />
                </div>
              }
            />
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {active.map((item) => {
              const short = item.price - balance
              return (
                <div key={item.id} className="group flex flex-col overflow-hidden rounded-lg border border-border bg-surface">
                  <ItemVisual item={item} className="h-24 w-full" />
                  <div className="flex flex-1 flex-col gap-2 p-3">
                    <p className="text-sm leading-snug font-medium">{item.name}</p>
                    <div className="mt-auto flex items-center gap-1">
                      <span className="flex flex-1 items-center gap-1 text-sm tabular-nums">
                        <Coins className="size-3.5 text-tone-violet-dot" />
                        {item.price}
                      </span>
                      <Button size="icon-sm" variant="ghost" aria-label={`Edit ${item.name}`} className="opacity-0 group-focus-within:opacity-100 group-hover:opacity-100" onClick={() => setEditing(item)}>
                        <Pencil />
                      </Button>
                      <Button size="icon-sm" variant="ghost" aria-label={`Archive ${item.name}`} className="opacity-0 group-focus-within:opacity-100 group-hover:opacity-100" onClick={() => archive(item, true)}>
                        <Archive />
                      </Button>
                      <Tooltip content={short > 0 ? `${plural(short, 'more token')} needed` : null}>
                        <span>
                          <Button size="sm" variant="secondary" disabled={short > 0} onClick={() => setBuying(item)}>
                            Buy
                          </Button>
                        </span>
                      </Tooltip>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {archived.length > 0 && (
          <div className="space-y-2">
            <button className="text-xs text-fg-subtle hover:text-fg" onClick={() => setShowArchived((v) => !v)} aria-expanded={showArchived}>
              {showArchived ? 'Hide' : 'Show'} archived ({archived.length})
            </button>
            {showArchived &&
              archived.map((item) => (
                <div key={item.id} className="flex items-center gap-3 rounded-md border border-border px-3 py-2 text-sm text-fg-muted">
                  <span className="flex-1">
                    {item.emoji} {item.name} · {item.price}
                  </span>
                  <Button size="xs" variant="ghost" onClick={() => archive(item, false)}>
                    <ArchiveRestore />
                    Restore
                  </Button>
                </div>
              ))}
          </div>
        )}
      </div>

      <div className="space-y-6">
        <section className="space-y-2">
          <p className="text-xs font-medium text-fg-subtle">Purchases</p>
          {shop.isPending ? (
            <SkeletonRows rows={2} />
          ) : !shop.data?.purchases.length ? (
            <p className="text-sm text-fg-muted">What you buy shows here; tick it once you've taken the treat.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
              {shop.data.purchases.map((p) => (
                <li key={p.id} className="flex items-center gap-3 px-3 py-2">
                  <Checkbox checked={p.redeemed_at !== null} onCheckedChange={(v) => redeem.mutate({ id: p.id, redeemed: v === true })} aria-label={`${p.name} redeemed`} />
                  <span className={cn('min-w-0 flex-1 truncate text-sm', p.redeemed_at && 'text-fg-subtle line-through decoration-1')}>
                    {p.emoji} {p.name}
                  </span>
                  <span className="text-xs whitespace-nowrap text-fg-subtle">{absoluteDate(p.bought_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="space-y-2" id="chests">
          <p className="text-xs font-medium text-fg-subtle">Chests opened</p>
          {chests.isPending ? (
            <SkeletonRows rows={2} />
          ) : !chests.data?.length ? (
            <p className="text-sm text-fg-muted">Every {summary.data?.chests.goal ?? 30} applications unlock a chest with 1 to 10 tokens.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {chests.data.map((c) => (
                <li key={c.id} className="flex items-center gap-2">
                  <Package className="size-3.5 text-tone-violet-dot" />
                  <span className="flex-1">Chest #{c.ordinal}</span>
                  <span className="text-xs text-fg-subtle">{absoluteDate(c.opened_at)}</span>
                  <span className="w-10 text-right font-medium tabular-nums">+{c.tokens}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="space-y-2">
          <p className="text-xs font-medium text-fg-subtle">Token history</p>
          {tokens.isPending ? (
            <SkeletonRows rows={2} />
          ) : !tokens.data?.ledger.length ? (
            <p className="text-sm text-fg-muted">No tokens yet.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {tokens.data.ledger.slice(0, 20).map((e) => (
                <li key={e.id} className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-fg-muted">{e.note || e.kind}</span>
                  <span className="text-xs text-fg-subtle">{absoluteDate(e.at)}</span>
                  <span className={cn('w-10 text-right font-medium tabular-nums', e.amount > 0 ? 'text-success-fg' : 'text-fg-muted')}>
                    {e.amount > 0 ? `+${e.amount}` : e.amount}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <ItemDialog key={editing === 'new' ? 'new' : (editing?.id ?? 'none')} item={editing === 'new' ? null : editing} open={editing !== null} onOpenChange={(o) => !o && setEditing(null)} />
      <BuyDialog item={buying} balance={balance} onClose={() => setBuying(null)} />
      <ChestDialog open={opening} onOpenChange={setOpening} />
    </div>
  )
}
