import { useEffect, useState } from 'react'
import { RefreshCw, TrendingUp, TrendingDown } from 'lucide-react'
import clsx from 'clsx'

interface EventSeries {
  series_symbol: string
  name: string
  category: string
  status: string
  underlying: string
}

interface EventContract {
  symbol: string
  event_symbol: string
  series_symbol: string
  question: string
  expiration: string
  underlying: string
  status: string
  series_name: string
  // from snapshot
  yes_price?: number
  no_price?: number
  yes_bid?: number
  yes_ask?: number
  volume?: number
  open_interest?: number
}

interface OrderForm {
  symbol: string
  question: string
  outcome: 'yes' | 'no'
  quantity: number
  limit_price: number
}

export default function Events() {
  const [series, setSeries]         = useState<EventSeries[]>([])
  const [contracts, setContracts]   = useState<EventContract[]>([])
  const [loading, setLoading]       = useState(false)
  const [order, setOrder]           = useState<OrderForm | null>(null)
  const [orderStatus, setOrderStatus] = useState<string>('')
  const [selectedSeries, setSelectedSeries] = useState<string>('all')

  const loadSeries = async () => {
    try {
      const d: EventSeries[] = await fetch('/api/events/series').then(r => r.json())
      setSeries(d)
      return d
    } catch {
      return []
    }
  }

  const loadContracts = async (seriesList: EventSeries[]) => {
    setLoading(true)
    const all: EventContract[] = []
    const target = selectedSeries === 'all' ? seriesList.slice(0, 8) : seriesList.filter(s => s.series_symbol === selectedSeries)
    for (const s of target) {
      try {
        const cs: EventContract[] = await fetch(`/api/events/contracts/${s.series_symbol}`).then(r => r.json())
        cs.forEach(c => { c.series_name = s.name })
        all.push(...cs)
      } catch { /* ignore */ }
    }

    // Fetch snapshots in one call
    const syms = all.map(c => c.symbol).filter(Boolean)
    if (syms.length > 0) {
      try {
        const snaps = await fetch(`/api/events/snapshot?symbols=${syms.join(',')}`).then(r => r.json())
        const snapMap: Record<string, any> = {}
        for (const s of snaps) snapMap[s.symbol] = s
        all.forEach(c => {
          const sn = snapMap[c.symbol]
          if (sn) {
            c.yes_price = sn.yes_price || sn.yes_ask || 0
            c.no_price  = sn.no_price  || (c.yes_price ? Math.round((1 - c.yes_price) * 100) / 100 : 0)
            c.yes_bid   = sn.yes_bid || 0
            c.yes_ask   = sn.yes_ask || 0
            c.volume    = sn.volume || 0
            c.open_interest = sn.open_interest || 0
          }
        })
      } catch { /* non-fatal */ }
    }

    setContracts(all)
    setLoading(false)
  }

  const refresh = async () => {
    const s = await loadSeries()
    if (s.length > 0) await loadContracts(s)
  }

  useEffect(() => { refresh() }, [])
  useEffect(() => { if (series.length > 0) loadContracts(series) }, [selectedSeries])

  const placeOrder = async () => {
    if (!order) return
    setOrderStatus('Placing order…')
    try {
      const resp = await fetch('/api/events/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order),
      })
      const data = await resp.json()
      if (data.order_id) {
        setOrderStatus(`✓ Order placed — ID: ${data.order_id}`)
        setOrder(null)
      } else {
        setOrderStatus(`Error: ${JSON.stringify(data)}`)
      }
    } catch (e: any) {
      setOrderStatus(`Error: ${e.message}`)
    }
  }

  const openOrder = (c: EventContract, outcome: 'yes' | 'no') => {
    const price = outcome === 'yes' ? (c.yes_ask || c.yes_price || 0.5) : (c.no_price || 0.5)
    setOrder({
      symbol: c.symbol,
      question: c.question || c.series_name,
      outcome,
      quantity: 10,
      limit_price: price,
    })
    setOrderStatus('')
  }

  const filteredContracts = contracts.filter(c =>
    selectedSeries === 'all' || c.series_symbol === selectedSeries
  ).filter(c => c.yes_price && c.yes_price > 0)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Prediction Markets</h1>
        <button onClick={refresh} className="flex items-center gap-2 px-3 py-1.5 rounded text-xs bg-[#21262d] text-gray-400 hover:text-white">
          <RefreshCw size={12} className={clsx(loading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      {/* Series filter */}
      {series.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setSelectedSeries('all')}
            className={clsx('px-3 py-1 rounded text-xs', selectedSeries === 'all' ? 'bg-accent text-black' : 'bg-[#21262d] text-gray-400 hover:text-white')}
          >
            All Series
          </button>
          {series.map(s => (
            <button
              key={s.series_symbol}
              onClick={() => setSelectedSeries(s.series_symbol)}
              className={clsx('px-3 py-1 rounded text-xs', selectedSeries === s.series_symbol ? 'bg-accent text-black' : 'bg-[#21262d] text-gray-400 hover:text-white')}
            >
              {s.name || s.series_symbol}
            </button>
          ))}
        </div>
      )}

      {/* Contracts grid */}
      {loading && (
        <div className="text-gray-500 text-sm text-center py-12">Loading prediction markets…</div>
      )}

      {!loading && filteredContracts.length === 0 && (
        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-12 text-center text-gray-600">
          {series.length === 0
            ? 'No prediction market data — Webull event markets may require additional API access.'
            : 'No open contracts with live prices found.'}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3">
        {filteredContracts.map(c => {
          const yesPrice = c.yes_price || 0
          const noPrice  = c.no_price  || Math.round((1 - yesPrice) * 100) / 100
          const yesPct   = Math.round(yesPrice * 100)
          const noPct    = Math.round(noPrice  * 100)

          return (
            <div key={c.symbol} className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-white mb-1 leading-snug">
                    {c.question || c.series_name}
                  </div>
                  <div className="flex gap-3 text-xs text-gray-500">
                    {c.underlying && <span>Underlying: <span className="text-gray-300">{c.underlying}</span></span>}
                    {c.expiration && <span>Expires: <span className="text-gray-300">{c.expiration}</span></span>}
                    {c.volume != null && c.volume > 0 && <span>Vol: {c.volume.toLocaleString()}</span>}
                    {c.open_interest != null && c.open_interest > 0 && <span>OI: {c.open_interest.toLocaleString()}</span>}
                  </div>

                  {/* Probability bar */}
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex-1 h-2 rounded-full bg-[#21262d] overflow-hidden">
                      <div className="h-full bg-green-trade/60 rounded-full" style={{ width: `${yesPct}%` }} />
                    </div>
                    <span className="text-xs text-gray-500 w-20 shrink-0">
                      {yesPct}% YES / {noPct}% NO
                    </span>
                  </div>
                </div>

                {/* Prices + buttons */}
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => openOrder(c, 'yes')}
                    className="flex flex-col items-center px-3 py-2 rounded bg-green-trade/10 hover:bg-green-trade/20 border border-green-trade/20 transition-colors"
                  >
                    <div className="flex items-center gap-1 text-xs text-green-trade font-semibold">
                      <TrendingUp size={10} /> YES
                    </div>
                    <div className="text-white font-bold text-sm">${yesPrice.toFixed(2)}</div>
                  </button>
                  <button
                    onClick={() => openOrder(c, 'no')}
                    className="flex flex-col items-center px-3 py-2 rounded bg-red-trade/10 hover:bg-red-trade/20 border border-red-trade/20 transition-colors"
                  >
                    <div className="flex items-center gap-1 text-xs text-red-trade font-semibold">
                      <TrendingDown size={10} /> NO
                    </div>
                    <div className="text-white font-bold text-sm">${noPrice.toFixed(2)}</div>
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Order modal */}
      {order && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-6 w-full max-w-md space-y-4">
            <h2 className="text-base font-bold text-white">
              Buy <span className={order.outcome === 'yes' ? 'text-green-trade' : 'text-red-trade'}>{order.outcome.toUpperCase()}</span>
            </h2>
            <div className="text-xs text-gray-400">{order.question}</div>
            <div className="text-xs text-gray-600 font-mono">{order.symbol}</div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Contracts</label>
                <input
                  type="number" min={1} value={order.quantity}
                  onChange={e => setOrder(o => o ? { ...o, quantity: Math.max(1, Number(e.target.value)) } : null)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Limit Price ($0.01–$0.99)</label>
                <input
                  type="number" min={0.01} max={0.99} step={0.01} value={order.limit_price}
                  onChange={e => setOrder(o => o ? { ...o, limit_price: Math.min(0.99, Math.max(0.01, Number(e.target.value))) } : null)}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent"
                />
              </div>
            </div>

            <div className="text-xs text-gray-500 bg-[#0d1117] rounded p-2">
              Max payout: ${(order.quantity * 1).toFixed(2)} &nbsp;·&nbsp;
              Cost: ${(order.quantity * order.limit_price).toFixed(2)} &nbsp;·&nbsp;
              Max loss: ${(order.quantity * order.limit_price).toFixed(2)}
            </div>

            {orderStatus && (
              <div className={clsx('text-xs rounded p-2', orderStatus.startsWith('✓') ? 'text-green-trade bg-green-trade/10' : 'text-red-trade bg-red-trade/10')}>
                {orderStatus}
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={placeOrder} className={clsx(
                'flex-1 py-2 rounded font-semibold text-sm',
                order.outcome === 'yes' ? 'bg-green-trade text-black hover:opacity-90' : 'bg-red-trade text-white hover:opacity-90'
              )}>
                Place {order.outcome.toUpperCase()} Order
              </button>
              <button onClick={() => { setOrder(null); setOrderStatus('') }}
                className="flex-1 py-2 bg-[#21262d] text-gray-300 rounded text-sm hover:bg-[#30363d]">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
