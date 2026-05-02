import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Zap, Flame } from 'lucide-react'
import clsx from 'clsx'

interface Mover {
  symbol: string; name: string; price: number; change: number;
  change_pct: number; volume: number; market_cap: number;
}

function fmt(n: number) { return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function fmtVol(n: number) {
  if (n >= 1e9) return `${(n/1e9).toFixed(1)}B`
  if (n >= 1e6) return `${(n/1e6).toFixed(1)}M`
  if (n >= 1e3) return `${(n/1e3).toFixed(1)}K`
  return String(n)
}

function MoverTable({ rows, loading }: { rows: Mover[]; loading: boolean }) {
  if (loading) return (
    <div className="flex items-center justify-center py-12 text-gray-600 text-sm">
      <RefreshCw size={14} className="animate-spin mr-2" /> Loading…
    </div>
  )
  if (!rows.length) return <div className="py-8 text-center text-gray-600 text-sm">No data</div>

  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-gray-500 text-left border-b border-[#21262d]">
          <th className="pb-2 pr-3">Symbol</th>
          <th className="pb-2 pr-3 hidden sm:table-cell">Name</th>
          <th className="pb-2 pr-3 text-right">Price</th>
          <th className="pb-2 pr-3 text-right">Change</th>
          <th className="pb-2 pr-3 text-right">% Change</th>
          <th className="pb-2 text-right">Volume</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.symbol + i} className="border-b border-[#21262d]/50 hover:bg-[#1c2128]">
            <td className="py-2 pr-3 font-bold text-white">{r.symbol}</td>
            <td className="py-2 pr-3 text-gray-400 hidden sm:table-cell truncate max-w-[140px]">{r.name}</td>
            <td className="py-2 pr-3 text-right text-white font-mono">{fmt(r.price)}</td>
            <td className={clsx('py-2 pr-3 text-right font-mono', r.change >= 0 ? 'text-green-trade' : 'text-red-trade')}>
              {r.change >= 0 ? '+' : ''}{fmt(r.change)}
            </td>
            <td className={clsx('py-2 pr-3 text-right font-semibold', r.change_pct >= 0 ? 'text-green-trade' : 'text-red-trade')}>
              {r.change_pct >= 0 ? '+' : ''}{r.change_pct.toFixed(2)}%
            </td>
            <td className="py-2 text-right text-gray-400 font-mono">{fmtVol(r.volume)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const TABS = [
  { id: 'gainers',  label: 'Top Gainers',  icon: TrendingUp },
  { id: 'losers',   label: 'Top Losers',   icon: TrendingDown },
  { id: 'actives',  label: 'Most Active',  icon: Zap },
  { id: 'trending', label: 'Trending',     icon: Flame },
]

export default function Market() {
  const [tab, setTab] = useState('gainers')
  const [data, setData] = useState<Record<string, Mover[]>>({ gainers: [], losers: [], actives: [], trending: [] })
  const [loading, setLoading] = useState(true)
  const [updated, setUpdated] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/market/movers')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const d = await res.json()
      setData({ gainers: d.gainers || [], losers: d.losers || [], actives: d.actives || [], trending: d.trending || [] })
      setUpdated(d.updated)
    } catch (e: any) {
      setError('Failed to load market data. Check internet connection.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 60s
  useEffect(() => {
    const t = setInterval(load, 60_000)
    return () => clearInterval(t)
  }, [load])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Market</h1>
        <div className="flex items-center gap-3">
          {updated && <span className="text-xs text-gray-600">Updated {new Date(updated).toLocaleTimeString()}</span>}
          <button onClick={load} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#21262d] text-gray-300 rounded text-xs hover:bg-[#30363d] disabled:opacity-50">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-trade/10 border border-red-trade/20 rounded px-4 py-3 text-sm text-red-trade">{error}</div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-[#161b22] border border-[#21262d] rounded-lg p-1 w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded-md text-sm transition-colors',
              tab === id ? 'bg-[#21262d] text-white' : 'text-gray-400 hover:text-gray-200')}>
            <Icon size={14} />
            {label}
            {!loading && data[id]?.length > 0 && (
              <span className="text-xs bg-[#30363d] text-gray-400 px-1.5 py-0.5 rounded-full">{data[id].length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Summary bar — top 3 of each */}
      {!loading && (
        <div className="grid grid-cols-4 gap-3">
          {TABS.map(({ id, label, icon: Icon }) => {
            const top = data[id]?.[0]
            return (
              <div key={id} className="bg-[#161b22] border border-[#21262d] rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-2">
                  <Icon size={11} /> {label}
                </div>
                {top ? (
                  <>
                    <div className="font-bold text-white text-sm">{top.symbol}</div>
                    <div className={clsx('text-xs font-semibold', top.change_pct >= 0 ? 'text-green-trade' : 'text-red-trade')}>
                      {top.change_pct >= 0 ? '+' : ''}{top.change_pct.toFixed(2)}%
                    </div>
                    <div className="text-xs text-gray-400">{fmt(top.price)}</div>
                  </>
                ) : <div className="text-xs text-gray-600">—</div>}
              </div>
            )
          })}
        </div>
      )}

      {/* Main table */}
      <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
        <MoverTable rows={data[tab] || []} loading={loading} />
      </div>
    </div>
  )
}
