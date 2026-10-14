import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
export const INTEGRATION_GUIDES: HowToGuide[] = [
  {
    id: 'lti-setup',
    category: 'integrations',
    links: [
      '/how-to#lti-setup-moodle',
      '/how-to#lti-setup-ilias',
      '/how-to#lti-manage',
      '/how-to#lti-teacher',
      '/how-to#lti-privacy',
      '/how-to#ts-lti-errors',
      'https://github.com/SebastianNagl/benger-platform/blob/main/docs/lms-integration.md',
    ],
  },
  {
    id: 'lti-setup-moodle',
    category: 'integrations',
    links: [
      '/how-to#lti-setup',
      '/how-to#lti-teacher',
      '/how-to#lti-grades',
      '/how-to#ts-lti-errors',
      'https://github.com/SebastianNagl/benger-platform/blob/main/docs/lms-integration.md',
    ],
  },
  {
    id: 'lti-setup-ilias',
    category: 'integrations',
    links: [
      '/how-to#lti-setup',
      '/how-to#lti-teacher',
      '/how-to#lti-privacy',
      '/how-to#ts-lti-errors',
      'https://github.com/SebastianNagl/benger-platform/blob/main/docs/lms-integration.md',
    ],
  },
  {
    id: 'lti-manage',
    category: 'integrations',
    links: [
      '/how-to#lti-setup',
      '/how-to#lti-grades',
      '/how-to#lti-privacy',
      '/how-to#ts-lti-errors',
    ],
  },
  {
    id: 'lti-teacher',
    category: 'integrations',
    links: [
      '/how-to#lti-collection',
      '/how-to#lti-grades',
      '/how-to#lti-setup',
      '/how-to#lti-privacy',
      'https://github.com/SebastianNagl/benger-platform/blob/main/docs/lms-integration.md',
    ],
  },
  {
    id: 'lti-collection',
    category: 'integrations',
    links: [
      '/how-to#lti-teacher',
      '/how-to#lti-grades',
      '/how-to#ts-lti-collection',
      'https://github.com/SebastianNagl/benger-platform/blob/main/docs/lms-integration.md',
    ],
  },
  {
    id: 'lti-grades',
    category: 'integrations',
    links: [
      '/how-to#lti-teacher',
      '/how-to#korrektur-review',
      '/how-to#ts-lti-grades',
      '/how-to#lti-manage',
      '/how-to#lti-privacy',
    ],
  },
  {
    id: 'lti-privacy',
    category: 'integrations',
    links: [
      'https://github.com/SebastianNagl/benger-platform/blob/main/docs/lms-integration.md',
      '/how-to#lti-setup',
      '/how-to#lti-manage',
      '/about/data-protection',
    ],
  },
]
