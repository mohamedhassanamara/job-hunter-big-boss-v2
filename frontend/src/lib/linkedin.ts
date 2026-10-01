/** A LinkedIn job search by geoId (mirrors backend services/linkedin.search_url): used by
 * Settings → LinkedIn's "Test link" so you can see where a geoId lands. */
export function linkedinSearchUrl(role: string, geoId: string): string {
  const params = new URLSearchParams({ keywords: role, geoId, f_TPR: 'r86400', sortBy: 'DD' })
  return `https://www.linkedin.com/jobs/search/?${params.toString().replace(/\+/g, '%20')}`
}
