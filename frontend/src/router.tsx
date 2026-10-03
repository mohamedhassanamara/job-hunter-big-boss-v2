import { createBrowserRouter } from 'react-router'
import { AppShell } from '@/components/app/AppShell'
import ApplicationsPage from '@/features/applications/ApplicationsPage'
import ContactsPage from '@/features/contacts/ContactsPage'
import CopilotPage from '@/features/copilot/CopilotPage'
import CVStudioPage from '@/features/cv-studio/CVStudioPage'
import DiscoverPage from '@/features/discover/DiscoverPage'
import ExperiencePage from '@/features/experience/ExperiencePage'
import ImportPage from '@/features/import/ImportPage'
import JobPage from '@/features/job/JobPage'
import LinkedInPage from '@/features/linkedin/LinkedInPage'
import MotivCenterPage from '@/features/motivation/MotivCenterPage'
import LetterStudioPage from '@/features/letter-studio/LetterStudioPage'
import NotFoundPage from '@/features/NotFoundPage'
import OutreachPage from '@/features/outreach/OutreachPage'
import PipelinePage from '@/features/pipeline/PipelinePage'
import SettingsPage from '@/features/settings/SettingsPage'
import StudioPage from '@/features/studio/StudioPage'
import TodayPage from '@/features/today/TodayPage'

export const router = createBrowserRouter([
  // The LinkedIn bookmark's import window: no app shell.
  { path: 'import', element: <ImportPage /> },
  {
    element: <AppShell />,
    children: [
      { index: true, element: <TodayPage /> },
      { path: 'discover', element: <DiscoverPage /> },
      { path: 'pipeline', element: <PipelinePage /> },
      { path: 'applications', element: <ApplicationsPage /> },
      { path: 'jobs/:id', element: <JobPage /> },
      { path: 'jobs/:id/cv', element: <CVStudioPage /> },
      { path: 'jobs/:id/letter', element: <LetterStudioPage /> },
      { path: 'outreach', element: <OutreachPage /> },
      { path: 'linkedin', element: <LinkedInPage /> },
      { path: 'copilot', element: <CopilotPage /> },
      { path: 'motivation', element: <MotivCenterPage /> },
      { path: 'studio', element: <StudioPage /> },
      { path: 'contacts', element: <ContactsPage /> },
      { path: 'experience', element: <ExperiencePage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
