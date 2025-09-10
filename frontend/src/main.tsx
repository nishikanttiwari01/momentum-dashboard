import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import './styles/tailwind.css'
import { router } from './router'
import { makeMsw } from './mocks/server'

const queryClient = new QueryClient()

// Start MSW in dev only
if (import.meta.env.DEV) {
  const worker = makeMsw()
  worker.start({ onUnhandledRequest: 'bypass' })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
)
