import { toast } from 'sonner'
import { TagInput } from '@/components/app/TagInput'
import { Input, Textarea } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { useState } from 'react'
import { Card, Field, SaveBar } from './sections'

interface OutreachValue {
  signature: { name: string; title: string; email: string; phone: string; photo_path: string; linkedin?: string; show_phone?: boolean; show_contacts?: boolean }
  sign_off: string
  opt_out: string
  sign_off_fr?: string
  opt_out_fr?: string
  banned_phrases: string[]
  max_words: number
  language: string
  approve_adds_to_queue?: boolean
}

/** Cold-email rules: signature and opt-out (added by code), banned phrases, length, language. */
export function OutreachSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.outreach as unknown as OutreachValue
  const profile = settings.values.profile as { full_name?: string; email?: string; phone?: string; headline?: string }
  const [value, setValue] = useState<OutreachValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  const sig = (k: keyof OutreachValue['signature'], v: string | boolean) => setValue({ ...value, signature: { ...value.signature, [k]: v } })
  const showPhone = value.signature.show_phone === true
  const showContacts = value.signature.show_contacts === true
  return (
    <Card
      title="Cold emails"
      description="Claude writes the hook, the value paragraph and the ask; code adds the greeting, the intro line and the signature below. Drafts breaking these rules are flagged and can't be approved."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setValue(initial)}
          onSave={() =>
            save.mutate(
              { key: 'outreach', value: value as unknown as Record<string, unknown> },
              { onSuccess: () => toast.success('Email rules saved'), onError: (e) => toast.error(e.message) },
            )
          }
        />
      }
    >
      <Field label="Approve adds to the send queue" hint="Approving an email in Review also queues it (the queue starts itself if it had emptied and a test email was sent). Remove from queue undoes it. Approval stays a deliberate key press.">
        <Switch checked={value.approve_adds_to_queue !== false} onCheckedChange={(v) => setValue({ ...value, approve_adds_to_queue: v })} aria-label="Approve adds to the send queue" />
      </Field>
      <Field label="Signature" hint="Empty fields use Settings → Candidate">
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder={profile.full_name || 'Name'} value={value.signature.name} onChange={(e) => sig('name', e.target.value)} aria-label="Signature name" />
          <Input placeholder={profile.headline || 'Title (e.g. Data Engineer)'} value={value.signature.title} onChange={(e) => sig('title', e.target.value)} aria-label="Signature title" />
          <Input placeholder={profile.email || 'Email'} value={value.signature.email} onChange={(e) => sig('email', e.target.value)} aria-label="Signature email" />
          <Input placeholder={profile.phone || 'Phone'} value={value.signature.phone} onChange={(e) => sig('phone', e.target.value)} disabled={!showPhone} aria-label="Signature phone" />
          <Input
            placeholder="LinkedIn (default: your profile link)"
            value={value.signature.linkedin ?? ''}
            onChange={(e) => sig('linkedin', e.target.value)}
            className="col-span-2"
            aria-label="Signature LinkedIn"
          />
          <Input
            placeholder="Photo (optional): path to an image file"
            value={value.signature.photo_path}
            onChange={(e) => sig('photo_path', e.target.value)}
            className="col-span-2"
            aria-label="Signature photo path"
          />
        </div>
      </Field>
      <Field label="Contact line" hint="Off by default: the email ends with the sign-off and your name. The attached CV carries your contacts.">
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={showContacts} onCheckedChange={(v) => sig('show_contacts', v)} aria-label="Show a contact line under your name" />
          {showContacts ? 'Title, email and LinkedIn under your name' : 'Ends with your name'}
        </label>
      </Field>
      {showContacts && (
        <Field label="Phone in the signature" hint="Off by default: the country code tells where you are. The CV keeps it either way.">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={showPhone} onCheckedChange={(v) => sig('show_phone', v)} aria-label="Show the phone number in the email signature" />
            {showPhone ? 'Shown under your name' : 'Hidden (email and LinkedIn only)'}
          </label>
        </Field>
      )}
      <Field label="Sign-off">
        <Input value={value.sign_off} onChange={(e) => setValue({ ...value, sign_off: e.target.value })} className="w-60" />
      </Field>
      <Field label="Last line" hint="Optional, after your name. Empty: none">
        <Textarea value={value.opt_out} onChange={(e) => setValue({ ...value, opt_out: e.target.value })} className="min-h-14" />
      </Field>
      <Field label="French emails" hint="Sign-off and last line when the email is in French">
        <div className="space-y-2">
          <Input value={value.sign_off_fr ?? 'Bien cordialement,'} onChange={(e) => setValue({ ...value, sign_off_fr: e.target.value })} className="w-60" aria-label="French sign-off" />
          <Textarea
            value={value.opt_out_fr ?? ''}
            onChange={(e) => setValue({ ...value, opt_out_fr: e.target.value })}
            className="min-h-14"
            aria-label="French last line"
          />
        </div>
      </Field>
      <Field label="Word limit" hint="Greeting + body + ask">
        <Input type="number" min={50} max={400} value={value.max_words} onChange={(e) => setValue({ ...value, max_words: Number(e.target.value) })} className="w-24" />
      </Field>
      <Field label="Language">
        <Select
          value={value.language}
          onValueChange={(v) => setValue({ ...value, language: v })}
          options={[
            { value: 'auto', label: "The listing's language" },
            { value: 'en', label: 'Always English' },
            { value: 'fr', label: 'Always French' },
            { value: 'es', label: 'Always Spanish' },
          ]}
          className="w-60"
        />
      </Field>
      <Field label="Banned phrases" hint="Generic openers and clichés; matched ignoring case and accents">
        <TagInput tags={value.banned_phrases} onChange={(banned_phrases) => setValue({ ...value, banned_phrases })} placeholder="add a phrase (Enter)" />
      </Field>
    </Card>
  )
}
