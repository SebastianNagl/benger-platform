import { translate } from '@/lib/utils/translate'

export default function MinimalPage() {
  return (
    <div>
      <h1>{translate('layout.minimal.pageTitle')}</h1>
      <p>{translate('layout.minimal.pageDescription')}</p>
    </div>
  )
}
