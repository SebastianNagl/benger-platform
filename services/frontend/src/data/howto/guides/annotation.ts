import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const ANNOTATION_GUIDES: HowToGuide[] = [
  {
    id: 'labeling-templates',
    category: 'annotation',
  },
  {
    id: 'edit-label-xml',
    category: 'annotation',
    links: ['https://labelstud.io/tags/'],
  },
  {
    id: 'annotation-instructions',
    category: 'annotation',
  },
]
