import { Compass } from 'lucide-react'
import { Link } from 'react-router'
import { EmptyState } from '@/components/app/states'
import { Button } from '@/components/ui/button'

export default function NotFoundPage() {
  return (
    <EmptyState
      icon={Compass}
      title="Page not found"
      description="This page doesn't exist. It may have moved."
      action={
        <Button asChild variant="default" size="sm">
          <Link to="/">Back to Today</Link>
        </Button>
      }
    />
  )
}
