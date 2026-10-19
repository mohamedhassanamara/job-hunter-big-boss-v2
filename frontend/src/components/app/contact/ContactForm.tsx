import { ClipboardPaste, TriangleAlert } from 'lucide-react'
import { useState, type Ref } from 'react'
import { toast } from 'sonner'
import { HunterFindButton, HunterVerifyButton } from '@/components/app/contact/HunterButton'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Kbd } from '@/components/ui/kbd'
import { Label } from '@/components/ui/label'
import { useParsePaste } from '@/lib/queries/getContact'
import type { ContactFields, HunterVerified, PasteParsed } from '@/lib/types'
import { cn } from '@/lib/utils'

const EMPTY: ContactFields = { full_name: '', title: '', email: '', linkedin_url: '' }
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

/** The quick entry form: name, title, email, LinkedIn. Paste a block from the Apollo extension
 * or LinkedIn and the fields fill in (you check them before saving). ⌘↵ saves. */
export function ContactForm({
  appId,
  companyName,
  initial,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
  withPaste = true,
  withHunter = true,
  quiet = false,
  pasteRef,
}: {
  appId: number
  companyName: string
  initial?: Partial<ContactFields>
  submitLabel: string
  pending: boolean
  onSubmit: (fields: ContactFields, via: 'found' | 'hunter') => void
  onCancel?: () => void
  withPaste?: boolean
  withHunter?: boolean
  /** Another button on the screen is the primary one. */
  quiet?: boolean
  pasteRef?: Ref<HTMLTextAreaElement>
}) {
  const [fields, setFields] = useState<ContactFields>({ ...EMPTY, ...initial })
  const [paste, setPaste] = useState('')
  const [parsed, setParsed] = useState<PasteParsed | null>(null)
  const [hunterEmail, setHunterEmail] = useState<string | null>(null)
  const [verified, setVerified] = useState<HunterVerified | null>(null)
  const parse = useParsePaste()
  const set = (k: keyof ContactFields, v: string) => setFields((f) => ({ ...f, [k]: v }))

  const fill = (text: string) => {
    if (!text.trim()) return
    parse.mutate(text, {
      onSuccess: (p) => {
        setParsed(p)
        setFields((f) => ({
          full_name: p.full_name ?? f.full_name,
          title: p.title ?? f.title,
          email: p.email ?? f.email,
          linkedin_url: p.linkedin_url ?? f.linkedin_url,
        }))
        const got = [p.full_name && 'name', p.title && 'title', p.email && 'email', p.linkedin_url && 'LinkedIn'].filter(Boolean)
        if (got.length) toast.success(`Filled ${got.join(', ')} from the paste`, { description: 'Check the fields, then save.' })
        else toast('Nothing recognisable in the paste', { description: 'Type the fields instead.' })
      },
      onError: (e) => toast.error(e.message),
    })
  }
  const otherCompany = parsed?.company && !fold(parsed.company).includes(fold(companyName)) && !fold(companyName).includes(fold(parsed.company))
  const valid = fields.full_name.trim().length > 1 && /\S+@\S+\.\S+/.test(fields.email)
  const submit = () => valid && !pending && onSubmit(fields, hunterEmail && hunterEmail === fields.email.trim() ? 'hunter' : 'found')

  return (
    <form
      className="space-y-3"
      data-tour="contact-form"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
          e.preventDefault()
          submit()
        }
      }}
    >
      {withPaste && (
        <div className="space-y-1.5">
          <Label htmlFor={`paste-${appId}`} className="flex items-center gap-1.5">
            <ClipboardPaste className="size-3.5 text-fg-subtle" />
            Paste from the Apollo extension or LinkedIn
          </Label>
          <Textarea
            id={`paste-${appId}`}
            ref={pasteRef}
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            onPaste={(e) => fill(e.clipboardData.getData('text'))}
            placeholder="Select the extension's panel (or the profile header), copy, and paste here. The fields below fill in."
            className="min-h-16 text-xs"
          />
          {paste.trim() && (
            <Button type="button" size="xs" variant="ghost" onClick={() => fill(paste)} disabled={parse.isPending}>
              Fill the fields from this text
            </Button>
          )}
        </div>
      )}
      {parsed && (parsed.notes.length > 0 || otherCompany) && (
        <div className="space-y-1 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
          {otherCompany && (
            <p className="flex items-center gap-1.5">
              <TriangleAlert className="size-3.5 shrink-0" />
              The paste says “{parsed.company}”, not {companyName}: is it the right person?
            </p>
          )}
          {parsed.notes.map((n) => (
            <p key={n}>{n}</p>
          ))}
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 max-lg:grid-cols-1">
        <Input value={fields.full_name} onChange={(e) => set('full_name', e.target.value)} placeholder="Full name" aria-label="Full name" autoComplete="off" />
        <Input value={fields.title} onChange={(e) => set('title', e.target.value)} placeholder="Job title" aria-label="Job title" autoComplete="off" />
        <div className="space-y-1">
          <Input
            value={fields.email}
            onChange={(e) => set('email', e.target.value)}
            placeholder="Work email (from the extension)"
            aria-label="Email"
            type="email"
            autoComplete="off"
            className={cn(hunterEmail && hunterEmail === fields.email && 'border-primary')}
          />
          {withHunter && fields.email.includes('@') && <HunterVerifyButton email={fields.email.trim()} result={verified} onResult={setVerified} />}
        </div>
        <Input value={fields.linkedin_url} onChange={(e) => set('linkedin_url', e.target.value)} placeholder="LinkedIn profile URL" aria-label="LinkedIn URL" autoComplete="off" />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" variant={quiet ? 'outline' : 'default'} disabled={!valid || pending}>
          {pending ? 'Saving…' : submitLabel}
          <Kbd className={quiet ? undefined : 'border-transparent bg-primary-hover text-primary-fg'}>⌘↵</Kbd>
        </Button>
        {onCancel && (
          <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
        {withHunter && (
          <HunterFindButton
            appId={appId}
            fullName={fields.full_name}
            onFound={(r) => {
              setHunterEmail(r.email)
              setFields((f) => ({ ...f, email: r.email ?? f.email, title: f.title || r.position || '', linkedin_url: f.linkedin_url || r.linkedin_url || '' }))
            }}
          />
        )}
        {!valid && (fields.full_name || fields.email) && <span className="text-xs text-fg-subtle">A name and a work email are needed.</span>}
      </div>
    </form>
  )
}
