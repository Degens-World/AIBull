import { useState, useEffect } from 'react'
import clsx from 'clsx'

const CRYPTO_BASES = new Set(['BTC','ETH','SOL','DOGE','ADA','XRP','AVAX','LINK','LTC','DOT','MATIC','UNI','SHIB','BCH','ATOM'])
const QUICK_CRYPTO = ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']
const QUICK_STOCKS = ['AAPL', 'TSLA', 'NVDA', 'SPY', 'QQQ']

function isCrypto(sym: string) {
  const s = sym.toUpperCase().replace('-USD', '').replace('USD', '')
  return CRYPTO_BASES.has(s) || sym.toUpperCase().endsWith('-USD')
}

export default function Trading({ liveQuotes }: any) {
  const [form, setForm] = useState({ symbol: 'AAPL', side: 'BUY', order_type: 'MARKET', quantity: 1, price: '' })
  const crypto = isCrypto(form.symbol)
  const [orders, setOrders] = useState<any[]>([])
  const [status, setStatus] = useState('')
  const [quote, setQuote] = useState<any>(null)

  const loadOrders = () => fetch('/api/orders').then(r => r.json()).then(setOrders).catch(() => {})

  useEffect(() => { loadOrders() }, [])
  useEffect(() => { const t = setInterval(loadOrders, 30000); return () => clearInterval(t) }, [])

  useEffect(() => {
    const q = liveQuotes[form.symbol.toUpperCase()]
    if (q) setQuote(q)
    else fetch(`/api/quote/${form.symbol.toUpperCase()}`).then(r => r.json()).then(setQuote).catch(() => {})
  }, [form.symbol, liveQuotes])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('Placing order…')
    try {
      const body: any = { symbol: form.symbol, side: form.side, order_type: form.order_type, quantity: Number(form.quantity) }
      if (form.order_type !== 'MARKET' && form.price) body.price = Number(form.price)
      const res = await fetch('/api/orders', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const data = await res.json()
      setStatus(`Order placed: ${data.order_id} — ${data.status}`)
      loadOrders()
    } catch {
      setStatus('Error placing order')
    }
  }

  const cancel = async (id: string) => {
    await fetch(`/api/orders/${id}`, { method: 'DELETE' })
    loadOrders()
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-white">Order Entry</h1>

      <div className="grid grid-cols-3 gap-6">
        {/* Order form */}
        <div className="col-span-1 bg-[#161b22] border border-[#21262d] rounded-lg p-5">
          {quote && (
            <div className="mb-4 p-3 bg-[#0d1117] rounded-md">
              <div className="text-lg font-bold text-white">${quote.price}</div>
              <div className={clsx('text-xs', quote.change_pct >= 0 ? 'text-green-trade' : 'text-red-trade')}>
                {quote.change_pct >= 0 ? '+' : ''}{quote.change_pct?.toFixed(2)}% today
              </div>
              <div className="text-xs text-gray-500 mt-1">Bid ${quote.bid} · Ask ${quote.ask}</div>
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Symbol</label>
              <input value={form.symbol} onChange={e => setForm(f => ({ ...f, symbol: e.target.value.toUpperCase() }))}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
              <div className="flex gap-1 mt-1.5 flex-wrap">
                {QUICK_STOCKS.map(s => (
                  <button key={s} type="button" onClick={() => setForm(f => ({ ...f, symbol: s }))}
                    className="text-xs px-2 py-0.5 rounded bg-[#21262d] text-gray-400 hover:text-white">{s}</button>
                ))}
                <span className="text-xs text-gray-600 px-1">│</span>
                {QUICK_CRYPTO.map(s => (
                  <button key={s} type="button" onClick={() => setForm(f => ({ ...f, symbol: s }))}
                    className="text-xs px-2 py-0.5 rounded bg-[#21262d] text-yellow-400 hover:text-yellow-200">{s}</button>
                ))}
              </div>
              {crypto && <div className="text-xs text-yellow-400 mt-1">⬡ Crypto — fractional qty supported · 24/7</div>}
            </div>

            <div className="grid grid-cols-2 gap-3">
              {['BUY', 'SELL'].map(s => (
                <button key={s} type="button" onClick={() => setForm(f => ({ ...f, side: s }))}
                  className={clsx('py-2 rounded text-sm font-semibold transition-colors',
                    form.side === s
                      ? s === 'BUY' ? 'bg-green-trade text-black' : 'bg-red-trade text-white'
                      : 'bg-[#21262d] text-gray-400 hover:text-white')}>
                  {s}
                </button>
              ))}
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Order Type</label>
              <select value={form.order_type} onChange={e => setForm(f => ({ ...f, order_type: e.target.value }))}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
                <option>MARKET</option>
                <option>LIMIT</option>
                <option>STOP</option>
                <option>STOP_LIMIT</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">
                Quantity {crypto && <span className="text-yellow-400">(fractional ok)</span>}
              </label>
              <input type="number" min={crypto ? '0.0001' : '1'} step={crypto ? '0.0001' : '1'}
                value={form.quantity} onChange={e => setForm(f => ({ ...f, quantity: Number(e.target.value) }))}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
            </div>

            {form.order_type !== 'MARKET' && (
              <div>
                <label className="text-xs text-gray-400 block mb-1">Price</label>
                <input type="number" step="0.01" value={form.price} onChange={e => setForm(f => ({ ...f, price: e.target.value }))}
                  className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
              </div>
            )}

            <button type="submit" className={clsx('w-full py-2.5 rounded font-semibold text-sm',
              form.side === 'BUY' ? 'bg-green-trade text-black hover:opacity-90' : 'bg-red-trade text-white hover:opacity-90')}>
              Place {form.side} Order
            </button>

            {status && <div className="text-xs text-accent">{status}</div>}
          </form>
        </div>

        {/* Order book */}
        <div className="col-span-2 bg-[#161b22] border border-[#21262d] rounded-lg p-5">
          <div className="text-sm font-semibold text-white mb-4">Order History</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 text-left">
                {['ID', 'Symbol', 'Side', 'Type', 'Qty', 'Fill Price', 'Status', 'Time', ''].map(h => (
                  <th key={h} className="pb-2 pr-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((o: any) => (
                <tr key={o.order_id} className="border-t border-[#21262d] hover:bg-[#1c2128]">
                  <td className="py-2 pr-3 font-mono text-gray-400 max-w-[80px] truncate">{o.order_id?.slice(0, 10)}…</td>
                  <td className="py-2 pr-3 font-semibold text-white">{o.symbol}</td>
                  <td className={clsx('py-2 pr-3 font-semibold', o.side === 'BUY' ? 'text-green-trade' : 'text-red-trade')}>{o.side}</td>
                  <td className="py-2 pr-3 text-gray-300">{o.order_type}</td>
                  <td className="py-2 pr-3 text-gray-300">{o.quantity}</td>
                  <td className="py-2 pr-3 text-gray-300">{o.filled_price ? `$${Number(o.filled_price).toFixed(2)}` : o.price ? `$${Number(o.price).toFixed(2)}` : 'MKT'}</td>
                  <td className={clsx('py-2 pr-3',
                    o.status === 'FILLED' ? 'text-green-trade' :
                    o.status === 'CANCELLED' ? 'text-gray-500' : 'text-yellow-400')}>
                    {o.status}{o.status === 'FILLED' && o.filled_qty ? ` (${o.filled_qty})` : ''}
                  </td>
                  <td className="py-2 pr-3 text-gray-500 text-xs">{o.created_at ? new Date(o.created_at).toLocaleTimeString() : ''}</td>
                  <td className="py-2">
                    {o.status === 'PENDING' && (
                      <button onClick={() => cancel(o.order_id)} className="text-red-trade hover:opacity-80 text-xs">Cancel</button>
                    )}
                  </td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr><td colSpan={9} className="py-6 text-center text-gray-600">No orders yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
