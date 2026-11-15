import type { HowToGuide } from '@/lib/howto'

// Structure only; the copy lives in src/locales/<locale>/howto.json
// under howToGuides.<id> (link labels in the same order as the hrefs).
// All three guides are about access keys, so they stay hidden while the
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
    links: ['/profile', '/how-to#api-zugaenge', '/how-to#api-round-trip'],
    searchTerms: [
      'benger_client',
      'BengerClient',
      '/api/custom-models',
      'generation-config/structures',
      'cost-estimate',
    ],
    requires: 'publicApi',
  },
  {
    id: 'api-round-trip',
    category: 'integrations',
    links: ['/how-to#api-research-workflow', '/how-to#export-import-project'],
    searchTerms: ['model_id_map', 'dry_run', 'ndjson_gz', '/project-imports'],
    requires: 'publicApi',
  },
]
