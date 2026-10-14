import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const ORGANIZATION_GUIDES: HowToGuide[] = [
  {
    id: 'org-context',
    category: 'organizations',
  },
  {
    id: 'org-roles',
    category: 'organizations',
  },
  {
    id: 'invite-members',
    category: 'organizations',
  },
  {
    id: 'org-groups',
    category: 'organizations',
  },
]
