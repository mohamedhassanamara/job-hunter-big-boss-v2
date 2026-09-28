import { toast } from 'sonner'
import { TagInput } from '@/components/app/TagInput'
import { Input, Textarea } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { useState } from 'react'
import { Card, Field, SaveBar } from './sections'

interface OutreachValue {
  signature: { name: string; title: string; email: string; phone: string; photo_path: string }
  sign_off: string
  opt_out: string
  banned_phrases: string[]
  max_words: number
  language: string
}

/** Cold-email rules: signature and opt-out (added by code), banned phrases, length, language. */
export function OutreachSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.outreach as unknown as OutreachValue
  const profile = settings.values.profile as { full_name?: string; email?: string; phone?: string; headline?: string }
  const [value, setValue] = useState<OutreachValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  const sig = (k: keyof OutreachValue['signature'], v: string) => setValue({ ...value, signature: { ...value.signature, [k]: v } })
  return (
    <Card
      title="Cold emails"
      description="Claude writes the greeting, 2–4 sentences and one ask; the signature and the opt-out line below are added by code. Drafts breaking these rules are flagged and can't be approved."
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
      <Field label="Signature" hint="Empty fields use Settings → Candidate">
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder={profile.full_name || 'Name'} value={value.signature.name} onChange={(e) => sig('name', e.target.value)} aria-label="Signature name" />
          <Input placeholder={profile.headline || 'Title (e.g. Data Engineer)'} value={value.signature.title} onChange={(e) => sig('title', e.target.value)} aria-label="Signature title" />
          <Input placeholder={profile.email || 'Email'} value={value.signature.email} onChange={(e) => sig('email', e.target.value)} aria-label="Signature email" />
          <Input placeholder={profile.phone || 'Phone'} value={value.signature.phone} onChange={(e) => sig('phone', e.target.value)} aria-label="Signature phone" />
          <Input
            placeholder="Photo (optional): path to an image file"
            value={value.signature.photo_path}
            onChange={(e) => sig('photo_path', e.target.value)}
            className="col-span-2"
            aria-label="Signature photo path"
          />
        </div>
      </Field>
      <Field label="Sign-off">
        <Input value={value.sign_off} onChange={(e) => setValue({ ...value, sign_off: e.target.value })} className="w-60" />
      </Field>
      <Field label="Opt-out line" hint="One polite line at the end">
        <Textarea value={value.opt_out} onChange={(e) => setValue({ ...value, opt_out: e.target.value })} className="min-h-14" />
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
