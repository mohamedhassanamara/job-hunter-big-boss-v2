import { createBrowserRouter } from 'react-router'
import { AppShell } from '@/components/app/AppShell'
import ContactsPage from '@/features/contacts/ContactsPage'
import CVStudioPage from '@/features/cv-studio/CVStudioPage'
import DiscoverPage from '@/features/discover/DiscoverPage'
import ExperiencePage from '@/features/experience/ExperiencePage'
import JobPage from '@/features/job/JobPage'
import NotFoundPage from '@/features/NotFoundPage'
import OutreachPage from '@/features/outreach/OutreachPage'
import PipelinePage from '@/features/pipeline/PipelinePage'
import SettingsPage from '@/features/settings/SettingsPage'
import TodayPage from '@/features/today/TodayPage'

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <TodayPage /> },
      { path: 'discover', element: <DiscoverPage /> },
      { path: 'pipeline', element: <PipelinePage /> },
      { path: 'jobs/:id', element: <JobPage /> },
      { path: 'jobs/:id/cv', element: <CVStudioPage /> },
      { path: 'outreach', element: <OutreachPage /> },
      { path: 'contacts', element: <ContactsPage /> },
      { path: 'experience', element: <ExperiencePage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
