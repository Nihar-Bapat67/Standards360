import { Link } from 'react-router-dom'

import { useT } from '../i18n'

export function ProductName({ small = false }: { small?: boolean }) {
  const t = useT()

  return (
    <Link
      to="/"
      aria-label={t('app.name')}
      className={`shrink-0 font-semibold text-text ${small ? 'text-[13px]' : 'text-[15px]'}`}
    >
      {t('app.name')}
    </Link>
  )
}