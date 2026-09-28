import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import './styles.css'
import { Landing } from './pages/Landing'
import { Atmosphere } from './components/Atmosphere'
import { RequireProfile } from './components/RequireProfile'
import { I18nProvider } from './i18n'

// The workspace pulls in Framer Motion and the whole findings panel. Someone arriving at the
// landing page should not download that before they have decided to use the product.
const Workspace = lazy(() => import('./pages/Workspace').then((m) => ({ default: m.Workspace })))
const Auth = lazy(() => import('./pages/Auth').then((m) => ({ default: m.Auth })))
const Results = lazy(() => import('./pages/Results').then((m) => ({ default: m.Results })))

function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Atmosphere variant="work" />
      <div className="flex items-center gap-3 text-sm text-secondary">
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-amber" />
        Loading the workspace
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <BrowserRouter>
        <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route
            path="/workspace"
            element={
              <RequireProfile>
                <Workspace />
              </RequireProfile>
            }
          />
          <Route
            path="/results/:id"
            element={
              <RequireProfile>
                <Results />
              </RequireProfile>
            }
          />
          <Route path="/login" element={<Auth mode="signin" />} />
          <Route path="/signup" element={<Auth mode="signup" />} />
          <Route path="*" element={<Landing />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </I18nProvider>
  </StrictMode>,
)
