import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const API_ACCESS_GUIDES: HowToGuide[] = [
  {
    id: 'api-zugaenge',
    category: 'integrations',
    links: ['/profile', '/users-organizations'],
  },
]
