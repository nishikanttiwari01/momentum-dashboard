import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import { qk } from './queryKeys'

export function useScreener(){
  return useQuery({ queryKey: qk.screener, queryFn: async () => (await api.get('/screener')).data })
}
export function useDetail(symbol: string){
  return useQuery({ queryKey: qk.detail(symbol), queryFn: async () => (await api.get(`/instruments/${symbol}/detail`)).data, enabled: !!symbol })
}
