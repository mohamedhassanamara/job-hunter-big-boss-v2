/** Exact heading texts by LinkedIn UI language (docs/LINKEDIN_EXTENSION_DESIGN.md §2.8.1).
 * English is the only language verified; add others when seen. */
export interface Labels {
  jobAbout: string
  jobTeam: string
  /** Profile section headings, in the order they usually appear: they bound the regions. */
  sections: Record<string, string>
  contact: string
}

export const LABELS: Record<string, Labels> = {
  en: {
    jobAbout: 'About the job',
    jobTeam: 'Meet the hiring team',
    sections: {
      about: 'About',
      highlights: 'Highlights',
      featured: 'Featured',
      activity: 'Activity',
      experience: 'Experience',
      education: 'Education',
      licenses: 'Licenses & certifications',
      projects: 'Projects',
      skills: 'Skills',
      recommendations: 'Recommendations',
      languages: 'Languages',
      interests: 'Interests',
    },
    contact: 'Contact info',
  },
}

export const UI_LANGUAGE = 'en'
export const labels = (): Labels => LABELS[UI_LANGUAGE]
