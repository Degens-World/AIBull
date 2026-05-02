import { useState, useEffect } from 'react'
import Dashboard from './pages/Dashboard'
import Trading from './pages/Trading'
import Portfolio from './pages/Portfolio'
import Performance from './pages/Performance'
import Crypto from './pages/Crypto'
import Strategies from './pages/Strategies'
import Market from './pages/Market'
import Settings from './pages/Settings'
import { LayoutDashboard, TrendingUp, Briefcase, Bot, Settings2, Wifi, WifiOff, BarChart2, Activity, Coins } from 'lucide-react'
import clsx from 'clsx'

type Page = 'dashboard' | 'trading' | 'portfolio' | 'performance' | 'crypto' | 'strategies' | 'market' | 'settings'

const NAV = [
  { id: 'dashboard'   as Page, label: 'Dashboard',   icon: LayoutDashboard },
  { id: 'trading'     as Page, label: 'Trading',      icon: TrendingUp },
  { id: 'portfolio'   as Page, label: 'Portfolio',    icon: Briefcase },
  { id: 'performance' as Page, label: 'Performance',  icon: Activity },
  { id: 'crypto'      as Page, label: 'Crypto',       icon: Coins },
  { id: 'strategies'  as Page, label: 'Strategies',   icon: Bot },
  { id: 'market'      as Page, label: 'Market',       icon: BarChart2 },
  { id: 'settings'    as Page, label: 'Settings',     icon: Settings2 },
]

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [connected, setConnected] = useState(false)
  const [liveQuotes, setLiveQuotes] = useState<Record<string, any>>({})
  const [logs, setLogs] = useState<any[]>([])
  const [engineStatus, setEngineStatus] = useState<any>(null)

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.hostname}:8421/ws`)
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'quote') {
        setLiveQuotes(prev => ({ ...prev, [msg.data.symbol]: msg.data }))
      } else if (msg.type === 'log') {
        setLogs(prev => [msg.data, ...prev].slice(0, 200))
      }
    }
    return () => ws.close()
  }, [])

  const [accounts, setAccounts] = useState<any[]>([])
  const [selectedAccount, setSelectedAccount] = useState<string>('')

  useEffect(() => {
    fetch('/api/engine/status').then(r => r.json()).then(setEngineStatus).catch(() => {})
    fetch('/api/logs').then(r => r.json()).then(d => setLogs(d.reverse())).catch(() => {})
    fetch('/api/accounts').then(r => r.json()).then(setAccounts).catch(() => {})
    fetch('/api/settings').then(r => r.json()).then(d => setSelectedAccount(d.selected_account_id || '')).catch(() => {})
  }, [])

  const selectAccount = async (id: string) => {
    setSelectedAccount(id)
    await fetch('/api/accounts/select', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: id }),
    })
  }

  const sharedProps = { liveQuotes, logs, engineStatus, selectedAccount, refreshEngine: () =>
    fetch('/api/engine/status').then(r => r.json()).then(setEngineStatus)
  }

  const accountLabel = accounts.find(a => a.id === selectedAccount)?.label
    ?? (accounts.length > 1 ? 'All Accounts' : accounts[0]?.label ?? '')

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-52 flex-shrink-0 bg-[#161b22] border-r border-[#21262d] flex flex-col">
        <div className="px-4 py-5 border-b border-[#21262d]">
          <div className="text-accent text-lg font-bold tracking-tight">AIBull</div>
          <div className="text-xs text-gray-500 mt-0.5">Automated Trading</div>
        </div>

        {/* Account selector */}
        {accounts.length > 0 && (
          <div className="px-3 py-2 border-b border-[#21262d]">
            <div className="text-xs text-gray-500 mb-1">Account</div>
            <select
              value={selectedAccount}
              onChange={e => selectAccount(e.target.value)}
              className="w-full bg-[#0d1117] border border-[#30363d] rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-accent"
            >
              {accounts.length > 1 && <option value="">All Accounts</option>}
              {accounts.map(a => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </div>
        )}

        <nav className="flex-1 px-2 py-3 space-y-1">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={clsx(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors',
                page === id
                  ? 'bg-[#21262d] text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#1c2128]'
              )}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </nav>

        <div className="px-4 py-3 border-t border-[#21262d] flex items-center gap-2 text-xs text-gray-500">
          {connected
            ? <><Wifi size={12} className="text-green-trade" /> Live</>
            : <><WifiOff size={12} className="text-red-trade" /> Offline</>
          }
          {engineStatus?.stub_mode && <span className="ml-auto text-yellow-400">STUB</span>}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-[#0d1117]">
        {page === 'dashboard'   && <Dashboard    {...sharedProps} />}
        {page === 'trading'     && <Trading      {...sharedProps} />}
        {page === 'portfolio'   && <Portfolio    {...sharedProps} />}
        {page === 'performance' && <Performance  {...sharedProps} />}
        {page === 'crypto'      && <Crypto       {...sharedProps} />}
        {page === 'strategies'  && <Strategies   {...sharedProps} />}
        {page === 'market'      && <Market />}
        {page === 'settings'    && <Settings />}
      </main>
    </div>
  )
}
