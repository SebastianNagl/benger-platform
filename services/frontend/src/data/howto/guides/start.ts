import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const START_GUIDES: HowToGuide[] = [
  {
    id: 'what-is-benger',
    category: 'start',
    links: ['/how-to#share-with-students', '/how-to#api-keys'],
  },
  {
    id: 'first-steps',
    category: 'start',
  },
  {
    id: 'navigation-overview',
    category: 'start',
  },
]
