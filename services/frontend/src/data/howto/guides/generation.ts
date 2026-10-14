import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const GENERATION_GUIDES: HowToGuide[] = [
  {
    id: 'generation-run',
    category: 'generation',
    links: ['/generations', '/models'],
  },
  {
    id: 'model-catalog',
    category: 'generation',
  },
  {
    id: 'api-keys',
    category: 'generation',
    links: ['/profile', '/how-to#custom-models'],
  },
  {
    id: 'custom-models',
    category: 'generation',
  },
]
