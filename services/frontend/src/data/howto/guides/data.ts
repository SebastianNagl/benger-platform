import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const DATA_GUIDES: HowToGuide[] = [
  {
    id: 'upload-data',
    category: 'data',
    links: ['/how-to#exam-file-fields'],
  },
  {
    id: 'exam-file-fields',
    category: 'data',
  },
  {
    id: 'export-import-project',
    category: 'data',
  },
]
