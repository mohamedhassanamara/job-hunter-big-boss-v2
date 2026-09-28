import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { NewContact } from '@/lib/types'

/** Name, title, email, LinkedIn: used for a lookup result and for adding a contact by hand. */
export function NewContactDialog({
  open,
  title,
  subtitle,
  submitLabel,
  pending,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  title: string
  subtitle?: string
  submitLabel: string
  pending: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (contact: NewContact) => void
}) {
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [email, setEmail] = useState('')
  const [linkedin, setLinkedin] = useState('')
  const submit = () =>
    name.trim() &&
    onSubmit({ full_name: name.trim(), title: role.trim() || null, email: email.trim() || null, linkedin_url: linkedin.trim() || null })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} className="max-w-md p-0">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="text-sm text-fg-muted">{subtitle}</p>}
        </div>
        <form
          className="space-y-3 px-5 py-4"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="nc-name">Full name</Label>
            <Input id="nc-name" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="First and last name" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nc-title">Job title</Label>
            <Input id="nc-title" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Head of Engineering" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="nc-email">Email</Label>
              <Input id="nc-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nc-linkedin">LinkedIn URL</Label>
              <Input id="nc-linkedin" value={linkedin} onChange={(e) => setLinkedin(e.target.value)} />
            </div>
          </div>
          <button type="submit" hidden />
        </form>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={submit} disabled={!name.trim() || pending}>
            {submitLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
