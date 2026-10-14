import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const PROJECT_GUIDES: HowToGuide[] = [
  {
    id: 'create-project',
    category: 'projects',
    links: ['/projects/create', '/how-to#project-kind'],
  },
  {
    id: 'project-kind',
    category: 'projects',
    links: ['/how-to#share-with-students'],
  },
  {
    id: 'exam-project-quick',
    category: 'projects',
    links: ['/how-to#exam-file-fields'],
  },
  {
    id: 'project-page',
    category: 'projects',
  },
  {
    id: 'assignment-and-limits',
    category: 'projects',
  },
  {
    id: 'timer-and-window',
    category: 'projects',
  },
  {
    id: 'safe-exam-browser',
    category: 'projects',
  },
  {
    id: 'archive-delete-restore',
    category: 'projects',
  },
]
