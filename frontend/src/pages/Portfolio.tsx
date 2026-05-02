import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import clsx from 'clsx'

const COLORS = ['#58a6ff', '#3fb950', '#f85149', '#e3b341', '#a371f7', '#79c0ff']

export default function Portfolio({ liveQuotes }: any) {
  const [positions, setPositions] = useState<any[]>([])
  const [account, setAccount] = useState<any>(null)

  useEffect(() => {
    fetch('/api/positions').then(r => r.json()).then(setPositions)
    fetch('/api/account').then(r => r.json()).then(setAccount)
  }, [])

  const enriched = positions.map(p => {
    const q = liveQuotes[p.symbol]
    const price = q?.price ?? p.current_price
    const value = price * p.quantity
    const pnl = (price - p.avg_cost) * p.quantity
    const pnlPct = ((price - p.avg_cost) / p.avg_cost) * 100
    return { ...p, live_price: price, market_value: value, pnl, pnl_pct: pnlPct }
  })

  const totalValue = enriched.reduce((s, p) => s + p.market_value, 0)
  const pieData = enriched.map(p => ({ name: p.symbol, value: p.market_value }))

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-white">Portfolio</h1>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Net Liquidation', value: account?.net_liquidation },
          { label: 'Buying Power',    value: account?.buying_power },
          { label: 'Cash Balance',    value: account?.cash_balance },
        ].map(({ label, value }) => (
          <div key={label} className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
            <div className="text-xs text-gray-400 mb-1">{label}</div>
            <div className="text-xl font-bold text-white">
              {value != null ? `$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Positions table */}
        <div className="col-span-2 bg-[#161b22] border border-[#21262d] rounded-lg p-5">
          <div className="text-sm font-semibold text-white mb-4">Positions</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 text-left">
                {['Symbol', 'Qty', 'Avg Cost', 'Price', 'Mkt Value', 'Unrealized P&L', '%'].map(h => (
                  <th key={h} className="pb-2 pr-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {enriched.map(p => (
                <tr key={p.symbol} className="border-t border-[#21262d] hover:bg-[#1c2128]">
                  <td className="py-2 pr-3 font-semibold text-white">{p.symbol}</td>
                  <td className="py-2 pr-3 text-gray-300">{p.quantity}</td>
                  <td className="py-2 pr-3 text-gray-300">${p.avg_cost?.toFixed(2)}</td>
                  <td className="py-2 pr-3 text-white">${p.live_price?.toFixed(2)}</td>
                  <td className="py-2 pr-3 text-gray-300">${p.market_value?.toFixed(2)}</td>
                  <td className={clsx('py-2 pr-3 font-semibold', p.pnl >= 0 ? 'text-green-trade' : 'text-red-trade')}>
                    {p.pnl >= 0 ? '+' : ''}${p.pnl?.toFixed(2)}
                  </td>
                  <td className={clsx('py-2', p.pnl_pct >= 0 ? 'text-green-trade' : 'text-red-trade')}>
                    {p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct?.toFixed(2)}%
                  </td>
                </tr>
              ))}
              {enriched.length === 0 && (
                <tr><td colSpan={7} className="py-6 text-center text-gray-600">No open positions</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Allocation pie */}
        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5">
          <div className="text-sm font-semibold text-white mb-4">Allocation</div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={2}>
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #21262d', fontSize: 12 }}
                formatter={(v: any) => `$${Number(v).toFixed(0)}`}
              />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-3 text-xs text-gray-400 text-center">
            Total: <span className="text-white font-semibold">${totalValue.toFixed(2)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
