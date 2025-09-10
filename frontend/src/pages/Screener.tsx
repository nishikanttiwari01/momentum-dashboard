import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api/client'

export default function Screener() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['screener'],
    queryFn: async () => (await api.get('/screener')).data,
  })

  if (isLoading) return <div className="p-6">Loading…</div>
  if (error) return <div className="p-6 text-red-600">Error loading screener.</div>

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Screener</h1>
      <pre className="text-xs bg-gray-50 p-4 rounded border overflow-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}
