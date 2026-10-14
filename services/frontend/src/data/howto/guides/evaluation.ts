import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const EVALUATION_GUIDES: HowToGuide[] = [
  {
    id: 'bewertungsbogen-upload-format',
    category: 'evaluation',
  },
  {
    id: 'evaluation-methods',
    category: 'evaluation',
    links: ['/how-to#api-keys'],
  },
  {
    id: 'immediate-evaluation',
    category: 'evaluation',
  },
  {
    id: 'batch-evaluation',
    category: 'evaluation',
  },
  {
    id: 'korrektur-review',
    category: 'evaluation',
  },
  {
    id: 'reports-leaderboards',
    category: 'evaluation',
  },
]
