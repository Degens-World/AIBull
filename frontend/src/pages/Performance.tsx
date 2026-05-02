import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line, ReferenceLine } from 'recharts'
import clsx from 'clsx'

function StatCard({ label, value, sub, color }: any) {
  return (
    <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className={clsx('text-xl font-bold', color ?? 'text-white')}>{value ?? '—'}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}

function pnlColor(v: number) { return v > 0 ? 'text-green-trade' : v < 0 ? 'text-red-trade' : 'text-gray-400' }
function fmt$(v: number) { return `${v >= 0 ? '+' : ''}$${Math.abs(v).toFixed(2)}` }

export default function Performance({ liveQuotes }: any) {
  const [orders, setOrders]     = useState<any[]>([])
  const [positions, setPositions] = useState<any[]>([])
  const [account, setAccount]   = useState<any>(null)

  useEffect(() => {
    fetch('/api/orders').then(r => r.json()).then(setOrders).catch(() => {})
    fetch('/api/positions').then(r => r.json()).then(setPositions).catch(() => {})
    fetch('/api/account').then(r => r.json()).then(setAccount).catch(() => {})
  }, [])

  const filled = orders.filter(o => o.status === 'FILLED')
  const buys   = filled.filter(o => o.side === 'BUY')
  const sells  = filled.filter(o => o.side === 'SELL')

  // Build per-symbol FIFO P&L from filled orders (sorted by time)
  const sorted = [...filled].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  const costBasis: Record<string, { qty: number; total: number }> = {}
  const realizedBySymbol: Record<string, number> = {}
  const tradeLog: any[] = []

  for (const o of sorted) {
    const sym = o.symbol
    const qty = Number(o.filled_qty || o.quantity)
    const price = Number(o.filled_price || o.price || 0)
    if (!costBasis[sym]) costBasis[sym] = { qty: 0, total: 0 }

    if (o.side === 'BUY') {
      costBasis[sym].qty   += qty
      costBasis[sym].total += qty * price
    } else if (o.side === 'SELL' && costBasis[sym].qty > 0) {
      const avgCost = costBasis[sym].total / costBasis[sym].qty
      const pnl     = (price - avgCost) * Math.min(qty, costBasis[sym].qty)
      realizedBySymbol[sym] = (realizedBySymbol[sym] ?? 0) + pnl
      costBasis[sym].qty   -= qty
      costBasis[sym].total -= avgCost * qty
      tradeLog.push({ ...o, pnl, avgCost })
    }
  }

  const totalRealized = Object.values(realizedBySymbol).reduce((s, v) => s + v, 0)
  const wins  = tradeLog.filter(t => t.pnl > 0).length
  const losses = tradeLog.filter(t => t.pnl < 0).length
  const winRate = tradeLog.length > 0 ? ((wins / tradeLog.length) * 100).toFixed(0) : '—'

  // Unrealized P&L from live quotes
  const unrealized = positions.reduce((sum, p) => {
    const livePrice = liveQuotes[p.symbol]?.price ?? p.current_price
    return sum + (livePrice - p.avg_cost) * p.quantity
  }, 0)

  // Bar chart: realized P&L by symbol
  const symPnlData = Object.entries(realizedBySymbol).map(([symbol, pnl]) => ({ symbol, pnl: Number(pnl.toFixed(2)) }))
    .sort((a, b) => b.pnl - a.pnl)

  // Cumulative P&L line chart
  let running = 0
  const cumulData = tradeLog.map((t, i) => { running += t.pnl; return { i: i + 1, pnl: Number(running.toFixed(2)) } })

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-white">Performance</h1>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Realized P&L" value={fmt$(totalRealized)}
          color={pnlColor(totalRealized)}
          sub={`${tradeLog.length} closed trade${tradeLog.length !== 1 ? 's' : ''}`} />
        <StatCard label="Unrealized P&L" value={fmt$(unrealized)}
          color={pnlColor(unrealized)}
          sub={`${positions.length} open position${positions.length !== 1 ? 's' : ''}`} />
        <StatCard label="Win Rate" value={winRate === '—' ? '—' : `${winRate}%`}
          color={Number(winRate) >= 50 ? 'text-green-trade' : 'text-red-trade'}
          sub={`${wins}W / ${losses}L`} />
        <StatCard label="Total Fills"
          value={filled.length}
          sub={`${buys.length} buys · ${sells.length} sells`} />
      </div>

      {/* Account summary row */}
      {account && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Net Liquidation', value: account.net_liquidation },
            { label: 'Buying Power',    value: account.buying_power },
            { label: 'Day P&L',         value: account.realized_pnl_day, colored: true },
          ].map(({ label, value, colored }) => (
            <div key={label} className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
              <div className="text-xs text-gray-400 mb-1">{label}</div>
              <div className={clsx('text-lg font-bold', colored ? pnlColor(value) : 'text-white')}>
                {value != null ? `${colored && value > 0 ? '+' : ''}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Cumulative P&L chart */}
        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5">
          <div className="text-sm font-semibold text-white mb-4">Cumulative Realized P&L</div>
          {cumulData.length > 1 ? (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={cumulData}>
                <XAxis dataKey="i" tick={{ fontSize: 10, fill: '#6e7681' }} />
                <YAxis tick={{ fontSize: 10, fill: '#6e7681' }} tickFormatter={v => `$${v}`} />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #21262d', fontSize: 12 }}
                  formatter={(v: any) => [`$${v}`, 'P&L']}
                />
                <ReferenceLine y={0} stroke="#30363d" />
                <Line type="monotone" dataKey="pnl" stroke="#58a6ff" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[180px] flex items-center justify-center text-gray-600 text-sm">No closed trades yet</div>
          )}
        </div>

        {/* P&L by symbol bar chart */}
        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5">
          <div className="text-sm font-semibold text-white mb-4">Realized P&L by Symbol</div>
          {symPnlData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={symPnlData}>
                <XAxis dataKey="symbol" tick={{ fontSize: 10, fill: '#6e7681' }} />
                <YAxis tick={{ fontSize: 10, fill: '#6e7681' }} tickFormatter={v => `$${v}`} />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #21262d', fontSize: 12 }}
                  formatter={(v: any) => [`$${v}`, 'P&L']}
                />
                <ReferenceLine y={0} stroke="#30363d" />
                <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                  {symPnlData.map((d, i) => <Cell key={i} fill={d.pnl >= 0 ? '#3fb950' : '#f85149'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[180px] flex items-center justify-center text-gray-600 text-sm">No closed trades yet</div>
          )}
        </div>
      </div>

      {/* Closed trades table */}
      <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5">
        <div className="text-sm font-semibold text-white mb-4">Closed Trade Log</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 text-left">
              {['Symbol', 'Qty', 'Avg Cost', 'Exit Price', 'Realized P&L', '% Gain', 'Time'].map(h => (
                <th key={h} className="pb-2 pr-4">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...tradeLog].reverse().map((t, i) => {
              const exitPrice = Number(t.filled_price || t.price)
              const pctGain = t.avgCost > 0 ? ((exitPrice - t.avgCost) / t.avgCost) * 100 : 0
              return (
              <tr key={i} className="border-t border-[#21262d] hover:bg-[#1c2128]">
                <td className="py-2 pr-4 font-semibold text-white">{t.symbol}</td>
                <td className="py-2 pr-4 text-gray-300">{t.filled_qty || t.quantity}</td>
                <td className="py-2 pr-4 text-gray-300">${Number(t.avgCost).toFixed(2)}</td>
                <td className="py-2 pr-4 text-gray-300">${exitPrice.toFixed(2)}</td>
                <td className={clsx('py-2 pr-4 font-semibold', pnlColor(t.pnl))}>{fmt$(t.pnl)}</td>
                <td className={clsx('py-2 pr-4 font-semibold', pnlColor(pctGain))}>
                  {pctGain >= 0 ? '+' : ''}{pctGain.toFixed(2)}%
                </td>
                <td className="py-2 pr-4 text-gray-500">{t.created_at ? new Date(t.created_at).toLocaleString() : ''}</td>
              </tr>
            )})}
            {tradeLog.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-gray-600">No closed trades yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
