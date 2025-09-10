import { http, HttpResponse } from 'msw'

// Import example payloads from repo root (/contracts/examples)
import screenerList from '../../../contracts/examples/screener-list.json'
import detail from '../../../contracts/examples/detail.json'
import alerts from '../../../contracts/examples/alerts.json'
import history from '../../../contracts/examples/history.json'
import settings from '../../../contracts/examples/settings.json'
import problem from '../../../contracts/examples/problem.json'

const API = '/api/v1'

export const handlers = [
  http.get(`${API}/screener`, () => HttpResponse.json(screenerList)),
  http.get(`${API}/instruments/:symbol/detail`, () => HttpResponse.json(detail)),
  http.get(`${API}/alerts`, () => HttpResponse.json(alerts)),
  http.post(`${API}/alerts`, async () => HttpResponse.json({ ok: true })),
  http.get(`${API}/history`, () => HttpResponse.json(history)),
  http.get(`${API}/settings`, () => HttpResponse.json(settings)),
  http.get(`${API}/_problem`, () => HttpResponse.json(problem, { status: 422 })),
]
