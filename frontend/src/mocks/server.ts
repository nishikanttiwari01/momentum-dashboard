// src/mocks/server.ts
import { setupWorker, type SetupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const makeMsw = (): SetupWorker => setupWorker(...handlers)
