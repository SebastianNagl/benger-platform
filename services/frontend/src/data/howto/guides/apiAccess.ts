import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
// Both guides are about access keys, so they stay hidden while the
// `public_api` feature flag is off (requires: 'publicApi').
export const API_ACCESS_GUIDES: HowToGuide[] = [
  {
    id: 'api-zugaenge',
    category: 'integrations',
    links: [
      '/profile',
      '/users-organizations',
      '/how-to#api-research-workflow',
    ],
    searchTerms: ['/api/v1/reference', '/api/v1/docs'],
    requires: 'publicApi',
  },
  {
    id: 'api-research-workflow',
    category: 'integrations',
    links: ['/profile', '/how-to#api-zugaenge'],
    searchTerms: ['benger_client', 'BengerClient', '/api/custom-models'],
    requires: 'publicApi',
  },
]
