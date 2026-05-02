import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, ShoppingCart } from 'lucide-react'
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import clsx from 'clsx'

function fmtPrice(n: number) {
  if (n >= 1000) return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  if (n >= 1)    return `$${n.toFixed(4)}`
  return `$${n.toFixed(6)}`
}
function fmtVol(n: number) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return String(n)
}
function pct(v: number) {
  return (
    <span className={clsx('font-semibold', v >= 0 ? 'text-green-trade' : 'text-red-trade')}>
      {v >= 0 ? '+' : ''}{v.toFixed(2)}%
    </span>
  )
}

function Sparkline({ data }: { data: number[] }) {
  if (!data?.length) return <div className="w-20 h-8 bg-[#0d1117] rounded" />
  const points = data.map((v, i) => ({ i, v }))
  const isUp = data[data.length - 1] >= data[0]
  return (
    <ResponsiveContainer width={80} height={32}>
      <LineChart data={points}>
        <Line type="monotone" dataKey="v" stroke={isUp ? '#3fb950' : '#f85149'}
          dot={false} strokeWidth={1.5} />
        <Tooltip
          contentStyle={{ background: '#161b22', border: '1px solid #21262d', fontSize: 10 }}
          formatter={(v: any) => [fmtPrice(Number(v)), '']}
          labelFormatter={() => ''}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

function QuickTrade({ coin, onClose }: { coin: any; onClose: () => void }) {
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [qty, setQty]   = useState('0.001')
  const [status, setStatus] = useState('')

  const submit = async () => {
    setStatus('Placing…')
    try {
      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: coin.base, side, order_type: 'MARKET', quantity: Number(qty) }),
      })
      const d = await res.json()
      setStatus(d.order_id ? `✓ ${side} ${qty} ${coin.base} — ${d.status}` : `Error: ${d.detail || 'Unknown'}`)
    } catch (e: any) {
      setStatus(`Error: ${e.message}`)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-6 w-80 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-bold text-white">{coin.base}</div>
            <div className="text-xs text-gray-400">{coin.name}</div>
          </div>
          <div className="text-right">
            <div className="text-white font-mono">{fmtPrice(coin.price)}</div>
            {pct(coin.change_pct)}
          </div>
        </div>

        <div className="flex gap-2">
          {(['BUY', 'SELL'] as const).map(s => (
            <button key={s} onClick={() => setSide(s)}
              className={clsx('flex-1 py-2 rounded font-semibold text-sm',
                side === s ? (s === 'BUY' ? 'bg-green-trade text-black' : 'bg-red-trade text-white')
                           : 'bg-[#21262d] text-gray-400')}>
              {s}
            </button>
          ))}
        </div>

        <div>
          <label className="text-xs text-gray-400 block mb-1">Quantity (fractional ok)</label>
          <input type="number" min="0.0001" step="0.0001" value={qty}
            onChange={e => setQty(e.target.value)}
            className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
          <div className="text-xs text-gray-500 mt-1">
            ≈ {fmtPrice(coin.price * Number(qty))} USD
          </div>
        </div>

        {status && <div className="text-xs text-accent">{status}</div>}

        <div className="flex gap-2">
          <button onClick={submit}
            className={clsx('flex-1 py-2 rounded font-semibold text-sm',
              side === 'BUY' ? 'bg-green-trade text-black' : 'bg-red-trade text-white')}>
            Place {side}
          </button>
          <button onClick={onClose} className="px-4 py-2 rounded bg-[#21262d] text-gray-400 text-sm">Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function Crypto(_props: any) {
  const [coins, setCoins]   = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState('')
  const [updated, setUpdated] = useState<string | null>(null)
  const [selected, setSelected] = useState<any | null>(null)
  const [sort, setSort]     = useState<{ key: string; asc: boolean }>({ key: 'market_rank', asc: true })

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const d = await fetch('/api/crypto/markets').then(r => r.json())
      setCoins(d)
      setUpdated(new Date().toISOString())
    } catch {
      setError('Failed to load crypto data')
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { const t = setInterval(load, 60_000); return () => clearInterval(t) }, [load])

  const toggleSort = (key: string) =>
    setSort(s => ({ key, asc: s.key === key ? !s.asc : true }))

  const sorted = [...coins].sort((a, b) => {
    const av = a[sort.key] ?? 0, bv = b[sort.key] ?? 0
    return sort.asc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
  })

  const Th = ({ k, label }: { k: string; label: string }) => (
    <th className="pb-2 pr-3 text-right cursor-pointer hover:text-gray-300 select-none"
      onClick={() => toggleSort(k)}>
      {label}{sort.key === k ? (sort.asc ? ' ↑' : ' ↓') : ''}
    </th>
  )

  // Hero row — top 5 at a glance
  const top5 = coins.slice(0, 5)

  return (
    <div className="p-6 space-y-6">
      {selected && <QuickTrade coin={selected} onClose={() => setSelected(null)} />}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Crypto</h1>
        <div className="flex items-center gap-3">
          {updated && <span className="text-xs text-gray-600">Updated {new Date(updated).toLocaleTimeString()}</span>}
          <button onClick={load} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#21262d] text-gray-300 rounded text-xs hover:bg-[#30363d] disabled:opacity-50">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {error && <div className="bg-red-trade/10 border border-red-trade/20 rounded px-4 py-3 text-sm text-red-trade">{error}</div>}

      {/* Hero cards */}
      {!loading && top5.length > 0 && (
        <div className="grid grid-cols-5 gap-3">
          {top5.map(c => (
            <div key={c.symbol}
              className="bg-[#161b22] border border-[#21262d] rounded-lg p-3 cursor-pointer hover:border-accent/50 transition-colors"
              onClick={() => setSelected(c)}>
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-white text-sm">{c.base}</span>
                <span className={clsx('text-xs', c.change_pct >= 0 ? 'text-green-trade' : 'text-red-trade')}>
                  {c.change_pct >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                </span>
              </div>
              <div className="text-xs text-gray-400 mb-2 truncate">{c.name}</div>
              <div className="font-mono text-white text-sm">{fmtPrice(c.price)}</div>
              <div className="mt-1">{pct(c.change_pct)}</div>
              <div className="mt-2">
                <Sparkline data={c.sparkline} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Main table */}
      <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="text-sm font-semibold text-white">All Assets</div>
          <div className="text-xs text-gray-500">Click row to trade · auto-refreshes every 60s</div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-600 text-sm">
            <RefreshCw size={14} className="animate-spin mr-2" /> Loading…
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 text-left border-b border-[#21262d]">
                <th className="pb-2 pr-3">Asset</th>
                <th className="pb-2 pr-3">Sparkline (1d)</th>
                <Th k="price"      label="Price" />
                <Th k="change_pct" label="24h %" />
                <Th k="change_7d"  label="7d %" />
                <Th k="volume"     label="Volume" />
                <th className="pb-2 text-right">Trade</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(c => (
                <tr key={c.symbol} className="border-b border-[#21262d]/50 hover:bg-[#1c2128] cursor-pointer"
                  onClick={() => setSelected(c)}>
                  <td className="py-2.5 pr-3">
                    <div className="font-bold text-white">{c.base}</div>
                    <div className="text-gray-500 text-[10px]">{c.name}</div>
                  </td>
                  <td className="py-2.5 pr-3">
                    <Sparkline data={c.sparkline} />
                  </td>
                  <td className="py-2.5 pr-3 text-right font-mono text-white">{fmtPrice(c.price)}</td>
                  <td className="py-2.5 pr-3 text-right">{pct(c.change_pct)}</td>
                  <td className="py-2.5 pr-3 text-right">{pct(c.change_7d)}</td>
                  <td className="py-2.5 pr-3 text-right text-gray-400 font-mono">{fmtVol(c.volume)}</td>
                  <td className="py-2.5 text-right">
                    <button
                      onClick={e => { e.stopPropagation(); setSelected(c) }}
                      className="flex items-center gap-1 ml-auto px-2 py-1 bg-[#21262d] hover:bg-accent/20 hover:text-accent rounded text-gray-400 transition-colors">
                      <ShoppingCart size={10} /> Trade
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
