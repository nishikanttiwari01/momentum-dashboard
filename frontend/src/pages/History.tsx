import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api/client'

export default function History() {
  const { data } = useQuery({
    queryKey: ['history'],
    queryFn: async () => (await api.get('/history')).data,
  })
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">History</h1>
      <pre className="text-xs bg-gray-50 p-4 rounded border overflow-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}
