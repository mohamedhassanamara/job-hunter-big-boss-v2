import { useState } from 'react'
import { toast } from 'sonner'
import { TagInput } from '@/components/app/TagInput'
import { Input, Textarea } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { Card, Field, SaveBar } from './sections'

type PerLanguage<T> = { fr: T; en: T }

interface CoverLetterValue {
  language: 'auto' | 'fr' | 'en'
  guide: string
  min_words: number
  max_words: number
  banned_phrases: PerLanguage<string[]>
  salutation: PerLanguage<string>
  closing: PerLanguage<string>
  years_statement_fr: string
  filename_pattern: string
}

/** Cover letter rules: the writing guide (given to Claude), length, per-language banned phrases,
 * salutation and closing formulas (added by code), and the download name. */
export function CoverLetterSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.cover_letter as unknown as CoverLetterValue
  const [value, setValue] = useState<CoverLetterValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  const set = (patch: Partial<CoverLetterValue>) => setValue({ ...value, ...patch })
  const perLang = <K extends 'banned_phrases' | 'salutation' | 'closing'>(key: K, lang: 'fr' | 'en', v: CoverLetterValue[K]['fr']) =>
    set({ [key]: { ...value[key], [lang]: v } } as Partial<CoverLetterValue>)
  return (
    <Card
      title="Cover letters"
      description="Claude writes the paragraphs and the closing ask from your approved CV; the header, date, salutation, closing formula and signature below are added by code. Letters breaking these rules are flagged and can't be approved."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setValue(initial)}
          onSave={() =>
            save.mutate(
              { key: 'cover_letter', value: value as unknown as Record<string, unknown> },
              { onSuccess: () => toast.success('Cover letter rules saved'), onError: (e) => toast.error(e.message) },
            )
          }
        />
      }
    >
      <div data-tour="settings-letter" className="space-y-4">
        <Field label="Language" hint="A job can override it in the studio">
          <Select
            value={value.language}
            onValueChange={(v) => set({ language: v as CoverLetterValue['language'] })}
            options={[
              { value: 'auto', label: "The listing's language" },
              { value: 'fr', label: 'Always French' },
              { value: 'en', label: 'Always English' },
            ]}
            className="w-60"
          />
        </Field>
        <Field label="Writing guide" hint="Your rules, given to Claude with every letter">
          <Textarea value={value.guide} onChange={(e) => set({ guide: e.target.value })} className="min-h-32" />
        </Field>
        <Field label="Length" hint="Words in the paragraphs and the ask">
          <div className="flex items-center gap-2 text-sm">
            <Input type="number" min={100} max={600} value={value.min_words} onChange={(e) => set({ min_words: Number(e.target.value) })} className="w-24" aria-label="Minimum words" />
            to
            <Input type="number" min={100} max={600} value={value.max_words} onChange={(e) => set({ max_words: Number(e.target.value) })} className="w-24" aria-label="Maximum words" />
            words
          </div>
        </Field>
        {(['fr', 'en'] as const).map((lang) => (
          <div key={lang} className="space-y-4 border-t border-border pt-4">
            <p className="text-sm font-medium">{lang === 'fr' ? 'French letters' : 'English letters'}</p>
            <Field label="Salutation" hint={lang === 'en' ? 'With a named contact: “Dear <name>,”' : undefined}>
              <Input value={value.salutation[lang]} onChange={(e) => perLang('salutation', lang, e.target.value)} className="w-80" />
            </Field>
            <Field label="Closing formula">
              <Textarea value={value.closing[lang]} onChange={(e) => perLang('closing', lang, e.target.value)} className="min-h-14" />
            </Field>
            <Field label="Banned phrases" hint="Clichés; matched ignoring case and accents">
              <TagInput tags={value.banned_phrases[lang]} onChange={(tags) => perLang('banned_phrases', lang, tags)} placeholder="add a phrase (Enter)" />
            </Field>
          </div>
        ))}
        <div className="space-y-4 border-t border-border pt-4">
          <Field label="French years wording" hint="Empty: the French of your statement in Settings → Candidate">
            <Input
              value={value.years_statement_fr}
              onChange={(e) => set({ years_statement_fr: e.target.value })}
              placeholder="3 ans d'expérience en ingénierie logicielle"
              className="w-96"
            />
          </Field>
          <Field label="Download name" hint="{full_name}, {company}, {job_title}, {version}">
            <Input value={value.filename_pattern} onChange={(e) => set({ filename_pattern: e.target.value })} className="w-96" />
          </Field>
        </div>
      </div>
    </Card>
  )
}
