import type { HowToGuide } from '@/lib/howto'
import { LTI_LAUNCH_ERROR_CODES } from '@/lib/lti/launchErrors'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const TROUBLESHOOTING_GUIDES: HowToGuide[] = [
  {
    id: 'ts-no-projects',
    category: 'troubleshooting',
    links: ['/how-to#org-context', '/how-to#org-groups'],
  },
  {
    id: 'ts-no-models',
    category: 'troubleshooting',
    links: ['/how-to#api-keys'],
  },
  {
    id: 'ts-generation-fails',
    category: 'troubleshooting',
  },
  {
    id: 'ts-import-validation',
    category: 'troubleshooting',
    links: ['/how-to#upload-data'],
  },
  {
    id: 'ts-unknown-component',
    category: 'troubleshooting',
    links: ['/how-to#edit-label-xml'],
  },
  {
    id: 'ts-import-button',
    category: 'troubleshooting',
  },
  {
    id: 'ts-lti-errors',
    category: 'troubleshooting',
    links: [
      '/how-to#lti-setup',
      '/how-to#lti-manage',
      '/how-to#lti-teacher',
      '/how-to#ts-lti-grades',
    ],
    // The error codes are searchable as typed, in every language.
    searchTerms: [...LTI_LAUNCH_ERROR_CODES],
  },
  {
    id: 'ts-lti-grades',
    category: 'troubleshooting',
    links: [
      '/how-to#lti-grades',
      '/how-to#lti-manage',
      '/how-to#lti-setup',
      '/how-to#ts-lti-collection',
    ],
  },
  {
    id: 'ts-lti-collection',
    category: 'troubleshooting',
    links: [
      '/how-to#lti-collection',
      '/how-to#ts-lti-grades',
      '/how-to#lti-grades',
    ],
  },
]
