import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react'
import clsx from 'clsx'

export default function Dashboard({ liveQuotes, logs, engineStatus }: any) {
  const [account, setAccount] = useState<any>(null)
  const [positions, setPositions] = useState<any[]>([])
  const [bars, setBars] = useState<any[]>([])
  const [chartSymbol, setChartSymbol] = useState('AAPL')

  useEffect(() => {
    fetch('/api/account').then(r => r.json()).then(setAccount)
    fetch('/api/positions').then(r => r.json()).then(setPositions)
  }, [])

  useEffect(() => {
    fetch(`/api/bars/${chartSymbol}?count=60`).then(r => r.json()).then(setBars)
  }, [chartSymbol])

  const topSymbols = ['AAPL', 'TSLA', 'NVDA', 'SPY', 'QQQ']

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-white">Dashboard</h1>

      {/* Account cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Net Liquidation', value: account?.net_liquidation, prefix: '$', icon: DollarSign },
          { label: 'Cash Balance',    value: account?.cash_balance,    prefix: '$', icon: DollarSign },
          { label: 'Unrealized P&L', value: account?.unrealized_pnl,  prefix: '$', icon: TrendingUp, colored: true },
          { label: "Day's P&L",      value: account?.realized_pnl_day, prefix: '$', icon: Activity, colored: true },
        ].map(({ label, value, prefix, icon: Icon, colored }) => (
          <div key={label} className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400">{label}</span>
              <Icon size={14} className="text-gray-500" />
            </div>
            <div className={clsx(
              'text-xl font-bold',
              colored && value != null && (value >= 0 ? 'text-green-trade' : 'text-red-trade'),
              (!colored || value == null) && 'text-white'
            )}>
              {value != null ? `${prefix}${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
            </div>
          </div>
        ))}
      </div>

      {/* Chart + quotes */}
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 bg-[#161b22] border border-[#21262d] rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-semibold text-white">{chartSymbol} — Daily</span>
            <div className="flex gap-2">
              {topSymbols.map(s => (
                <button key={s} onClick={() => setChartSymbol(s)}
                  className={clsx('text-xs px-2 py-1 rounded', chartSymbol === s ? 'bg-accent text-black' : 'bg-[#21262d] text-gray-400 hover:text-white')}>
                  {s}
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={bars}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: '#6e7681' }} tickLine={false} interval={9} />
              <YAxis tick={{ fontSize: 10, fill: '#6e7681' }} tickLine={false} domain={['auto', 'auto']} width={60} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: '#8b949e' }}
              />
              <Line dataKey="close" stroke="#58a6ff" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
          <div className="text-sm font-semibold text-white mb-3">Live Quotes</div>
          <div className="space-y-2">
            {topSymbols.map(sym => {
              const q = liveQuotes[sym]
              return (
                <div key={sym} className="flex items-center justify-between text-sm">
                  <span className="text-gray-300 font-medium w-12">{sym}</span>
                  <span className="text-white">{q ? `$${q.price}` : '—'}</span>
                  <span className={clsx('text-xs', q?.change_pct >= 0 ? 'text-green-trade' : 'text-red-trade')}>
                    {q ? `${q.change_pct >= 0 ? '+' : ''}${q.change_pct?.toFixed(2)}%` : ''}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Positions + Log */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
          <div className="text-sm font-semibold text-white mb-3">Open Positions</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 text-left">
                <th className="pb-2">Symbol</th><th className="pb-2">Qty</th>
                <th className="pb-2">Avg</th><th className="pb-2">P&L</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => (
                <tr key={p.symbol} className="border-t border-[#21262d]">
                  <td className="py-1.5 text-white font-medium">{p.symbol}</td>
                  <td className="py-1.5 text-gray-300">{p.quantity}</td>
                  <td className="py-1.5 text-gray-300">${p.avg_cost}</td>
                  <td className={clsx('py-1.5', p.unrealized_pnl >= 0 ? 'text-green-trade' : 'text-red-trade')}>
                    ${p.unrealized_pnl?.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-4 flex flex-col">
          <div className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            Agent Log
            <span className={clsx('text-xs px-1.5 py-0.5 rounded', engineStatus?.running ? 'bg-green-trade/20 text-green-trade' : 'bg-gray-700 text-gray-400')}>
              {engineStatus?.running ? 'RUNNING' : 'STOPPED'}
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-1 font-mono text-xs max-h-40">
            {logs.slice(0, 30).map((l: any, i: number) => {
              const ts = l.ts ? new Date(l.ts) : null
              const timeStr = ts ? ts.toLocaleString('en-US', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : ''
              return (
                <div key={i} className={clsx('flex gap-2 leading-relaxed',
                  l.level === 'ERROR' ? 'text-red-trade' :
                  l.level === 'SIGNAL' ? 'text-yellow-400' :
                  l.level === 'ORDER' ? 'text-green-trade' :
                  l.level === 'PAPER' ? 'text-accent' : 'text-gray-400'
                )}>
                  <span className="text-gray-600 shrink-0 tabular-nums">{timeStr}</span>
                  <span className="opacity-50 shrink-0">[{l.level}]</span>
                  <span className="break-all">{l.message}</span>
                </div>
              )
            })}
            {logs.length === 0 && <div className="text-gray-600">No logs yet</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
