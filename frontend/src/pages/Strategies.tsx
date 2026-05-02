import { useEffect, useState, useCallback } from 'react'
import { Plus, Trash2, Play, Square, ChevronDown, ChevronRight, RefreshCw, Zap } from 'lucide-react'
import clsx from 'clsx'

const DEFAULT_SMA = { fast_period: 9, slow_period: 21, quantity: 1, account_id: '' }
const DEFAULT_CLAUDE = {
  system_prompt: 'You are a disciplined stock trading assistant. Only trade when there is a clear signal with strong momentum. Protect capital first. Prefer stocks with high relative volume and clear trend direction. Never risk more than the max position size provided. IMPORTANT: This is a margin account under $25,000 — never buy and sell the same stock on the same calendar day (PDT rule). Always plan exits for the next trading day or later.',
  account_id: '',
  scan_limit: 10,
  max_position_usd: 500,
  extended_hours: false,
}

const PRESETS: Record<string, any> = {
  stocks_conservative: {
    key: 'stocks_conservative', label: 'Conservative', group: 'Stocks',
    name: 'Stocks — Conservative', description: 'Blue-chip large caps, small position sizes, capital preservation focus.',
    strategy_type: 'claude',
    symbols: ['AAPL','MSFT','GOOGL','AMZN','NVDA','SPY','QQQ','BRK-B','JPM','V'],
    config: {
      system_prompt: 'You are a conservative stock trading assistant managing real money. Your primary goal is capital preservation. Only enter high-conviction trades with very clear signals — strong trend, high relative volume, and low downside risk. Prefer HOLD over BUY when uncertain. Cut losses quickly. Avoid volatile momentum plays. Never risk more than the max position size provided.',
      scan_limit: 10, max_position_usd: 100, extended_hours: false, asset_class: 'stocks',
    },
  },
  stocks_moderate: {
    key: 'stocks_moderate', label: 'Moderate', group: 'Stocks',
    name: 'Stocks — Moderate', description: 'Auto-scans top gainers and most active. Balanced risk/reward.',
    strategy_type: 'claude', symbols: [],
    config: {
      system_prompt: 'You are a disciplined stock trading assistant. Trade when there is a clear signal with strong momentum and favorable risk/reward. Balance capital growth with protection. Prefer stocks with high relative volume and clear trend direction. Accept moderate drawdowns for good setups. Never risk more than the max position size provided.',
      scan_limit: 10, max_position_usd: 300, extended_hours: false, asset_class: 'stocks',
    },
  },
  stocks_aggressive: {
    key: 'stocks_aggressive', label: 'Aggressive', group: 'Stocks',
    name: 'Stocks — Aggressive', description: 'Momentum-driven, scans top 15 gainers and most active. High risk/reward.',
    strategy_type: 'claude', symbols: [],
    config: {
      system_prompt: 'You are an aggressive momentum stock trader. Hunt for high-velocity moves with strong volume confirmation. Enter early on breakouts and ride momentum. Be willing to accept higher volatility for larger gains. Cut losers fast. Scale into winners. Prioritize stocks with the highest relative volume and biggest percentage moves. Never exceed the max position size provided.',
      scan_limit: 15, max_position_usd: 750, extended_hours: true, asset_class: 'stocks',
    },
  },
  crypto_conservative: {
    key: 'crypto_conservative', label: 'Conservative', group: 'Crypto',
    name: 'Crypto — Conservative', description: 'BTC and ETH only, small positions, long-term hold bias.',
    strategy_type: 'claude', symbols: ['BTC','ETH'],
    config: {
      system_prompt: 'You are a conservative crypto trading assistant. Only trade Bitcoin (BTC) and Ethereum (ETH) — the most established assets. Primary goal is capital preservation. Only enter on strong dip-buying opportunities with clear support levels. Prefer HOLD over BUY during uncertainty. Use fractional quantities. Never risk more than the max position size provided.',
      scan_limit: 5, max_position_usd: 50, extended_hours: false, asset_class: 'crypto',
    },
  },
  crypto_moderate: {
    key: 'crypto_moderate', label: 'Moderate', group: 'Crypto',
    name: 'Crypto — Moderate', description: 'Top 8 cryptos, balanced position sizes, trend-following.',
    strategy_type: 'claude', symbols: ['BTC','ETH','SOL','XRP','DOGE','ADA','AVAX','LINK'],
    config: {
      system_prompt: 'You are a balanced crypto trading assistant. Trade major cryptocurrencies with clear trend signals and volume confirmation. Use fractional quantities appropriate to each asset\'s price. Balance between capturing upside and protecting against downside. Crypto trades 24/7 — be mindful of overnight positions and weekend volatility. Never risk more than the max position size provided.',
      scan_limit: 8, max_position_usd: 200, extended_hours: false, asset_class: 'crypto',
    },
  },
  crypto_aggressive: {
    key: 'crypto_aggressive', label: 'Aggressive', group: 'Crypto',
    name: 'Crypto — Aggressive', description: 'Full 18-coin scan, momentum-driven, 24/7 active trading.',
    strategy_type: 'claude', symbols: [],
    config: {
      system_prompt: 'You are an aggressive crypto momentum trader operating 24/7. Scan all major cryptocurrencies for breakouts, volume spikes, and momentum moves. Exploit high-volatility moves with well-sized fractional positions. Be willing to trade altcoins on strong signals. Cut losers quickly. Prioritize coins with the largest percentage moves and highest volume surges. Use fractional quantities. Never exceed the max position size provided.',
      scan_limit: 18, max_position_usd: 500, extended_hours: false, asset_class: 'crypto',
    },
  },
  options_conservative: {
    key: 'options_conservative', label: 'Conservative', group: 'Options',
    name: 'Options — Conservative', description: 'Single-leg calls/puts on large caps. Defined risk, no naked positions.',
    strategy_type: 'options', symbols: ['AAPL','MSFT','NVDA','SPY','QQQ'],
    config: {
      system_prompt: "You are a conservative options trader. Only buy single-leg calls or puts — no spreads, no naked selling. Pick contracts at least 2 weeks to expiration to avoid rapid theta decay. Only enter when the underlying has a very clear directional signal with high volume. Keep premium spend small. Choose PASS over any low-conviction setup. Max loss on any trade is the premium paid. Never exceed the max position size provided.",
      scan_limit: 5, max_position_usd: 200, extended_hours: false, asset_class: 'stocks',
    },
  },
  options_moderate: {
    key: 'options_moderate', label: 'Moderate', group: 'Options',
    name: 'Options — Moderate', description: 'Calls and puts on top movers. Balanced premium with momentum filters.',
    strategy_type: 'options', symbols: [],
    config: {
      system_prompt: "You are a momentum options trader. Buy calls when the underlying is in a clear uptrend with high relative volume. Buy puts when momentum is clearly breaking down. Target near-the-money options with 1-4 weeks to expiration for good delta exposure. Look for IV that is not excessively elevated. Only trade liquid contracts with open interest > 500 and bid > $0.10. PASS on any unclear or choppy setups. Never exceed the max position size provided.",
      scan_limit: 15, max_position_usd: 500, extended_hours: false, asset_class: 'stocks',
    },
  },
  options_aggressive: {
    key: 'options_aggressive', label: 'Aggressive', group: 'Options',
    name: 'Options — Aggressive', description: 'High-conviction directional plays on top gainers and momentum stocks.',
    strategy_type: 'options', symbols: [],
    config: {
      system_prompt: "You are an aggressive options momentum trader. Actively scan for breakout setups and buy calls on strong upward momentum or puts on clear breakdowns. Use near-the-money options with 1-3 weeks expiration for maximum leverage. Scale into high-conviction setups with multiple contracts. Cut losing positions quickly when the thesis is invalidated. Target contracts with high open interest and tight bid/ask spreads. Never exceed the max position size provided.",
      scan_limit: 25, max_position_usd: 1000, extended_hours: false, asset_class: 'stocks',
    },
  },
  events_conservative: {
    key: 'events_conservative', label: 'Conservative', group: 'Predictions',
    name: 'Predictions — Conservative', description: 'Scans Webull prediction markets. Bets only on high-conviction mispricing (>15% edge).',
    strategy_type: 'events', symbols: [],
    config: {
      system_prompt: "You are a conservative prediction market trader on Webull. Each contract pays $1 if correct, $0 if wrong — price IS the implied probability. Only bet when you are highly confident the market probability is wrong by at least 15%. Prefer PASS. Never bet on uncertain or close calls. Keep position sizes small.",
      scan_limit: 20, max_position_usd: 50, extended_hours: false, asset_class: 'events',
    },
  },
  events_moderate: {
    key: 'events_moderate', label: 'Moderate', group: 'Predictions',
    name: 'Predictions — Moderate', description: 'Balanced prediction market trading. Bets when >10% edge is identified.',
    strategy_type: 'events', symbols: [],
    config: {
      system_prompt: "You are a balanced prediction market trader on Webull. Each contract pays $1.00 if the event happens, $0.00 if it doesn't. You profit by finding markets where the price (implied probability) is significantly different from the true probability. Bet YES if you think the event is more likely than the market implies. Bet NO if you think it is less likely. Require at least 10% edge. Return [] if no contracts offer clear edge.",
      scan_limit: 30, max_position_usd: 150, extended_hours: false, asset_class: 'events',
    },
  },
  events_aggressive: {
    key: 'events_aggressive', label: 'Aggressive', group: 'Predictions',
    name: 'Predictions — Aggressive', description: 'Actively hunts mispriced prediction markets. Larger positions, lower conviction threshold.',
    strategy_type: 'events', symbols: [],
    config: {
      system_prompt: "You are an aggressive prediction market trader on Webull. Actively scan all open prediction contracts for mispriced probabilities. Each contract pays $1.00 win / $0.00 loss. Your edge is superior probability assessment. Use technical analysis, recent news, momentum, and market structure to assess true outcome probability vs the implied market price. Bet YES when probability is underpriced, NO when overpriced. Require at least 7% edge.",
      scan_limit: 50, max_position_usd: 300, extended_hours: false, asset_class: 'events',
    },
  },
  momentum_conservative: {
    key: 'momentum_conservative', label: 'Conservative', group: 'Momentum',
    name: 'Momentum — Conservative', description: '$2–$20 small-caps, 3x+ rel vol, 2 positions max, tight stops.',
    strategy_type: 'momentum', symbols: [],
    config: {
      system_prompt: "You are a conservative small-cap momentum trader. Universe: stocks priced $2–$20 only — never trade large-caps. Only enter setups with at least 3x relative volume and a very clear breakout. Maximum 2 positions simultaneously. Require 2.5:1 risk/reward minimum. Prefer PASS over any low-conviction setup. Keep initial position size small — capital preservation is priority.",
      scan_limit: 30, max_position_usd: 200, extended_hours: false, asset_class: 'stocks',
    },
  },
  momentum_moderate: {
    key: 'momentum_moderate', label: 'Moderate', group: 'Momentum',
    name: 'Momentum — Moderate', description: '$2–$20 universe, 2x+ rel vol, up to 3 positions, balanced risk.',
    strategy_type: 'momentum', symbols: [],
    config: {
      system_prompt: "You are a disciplined small-cap momentum day trader. Universe: stocks priced $2–$20 only — no mega-caps, no large-caps. Focus on 2x+ relative volume, strong intraday momentum, clear breakout patterns. Select up to 3 positions per tick. Require 2:1 risk/reward minimum. Use 70% initial position, hold 30% for add-on if momentum confirms. Cut losers immediately at stop. Never risk more than the allocated position size.",
      scan_limit: 40, max_position_usd: 400, extended_hours: false, asset_class: 'stocks',
    },
  },
  momentum_aggressive: {
    key: 'momentum_aggressive', label: 'Aggressive', group: 'Momentum',
    name: 'Momentum — Aggressive', description: '$2–$20 full scan, 2x+ rel vol, up to 5 positions, high conviction plays.',
    strategy_type: 'momentum', symbols: [],
    config: {
      system_prompt: "You are an aggressive small-cap momentum day trader operating in the $2–$20 universe. Hunt for stocks with explosive relative volume (2x+ over 3-month avg), strong momentum, and clear intraday breakout setups. Select 2–5 positions per tick. Allocate buying power proportionally: 2 positions=40% BP each, 3=30% each, 4=22.5% each, 5=18% each. Chunk entry: 70% initial size, 30% add-on if price confirms. Stop placement: recent swing low or max -5% from entry. Target minimum 2:1 risk/reward. Cut losers fast. Scale winners. Universe is strictly $2–$20 — never recommend large or mega-cap stocks.",
      scan_limit: 50, max_position_usd: 750, extended_hours: false, asset_class: 'stocks',
    },
  },
}

const RISK_COLORS: Record<string, string> = {
  Conservative: 'bg-blue-500/20 text-blue-400 border-blue-500/30 hover:bg-blue-500/30',
  Moderate:     'bg-yellow-500/20 text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/30',
  Aggressive:   'bg-red-trade/20 text-red-trade border-red-trade/30 hover:bg-red-trade/30',
}
const RISK_ACTIVE: Record<string, string> = {
  Conservative: 'bg-blue-500/40 text-blue-300 border-blue-400',
  Moderate:     'bg-yellow-500/40 text-yellow-300 border-yellow-400',
  Aggressive:   'bg-red-trade/40 text-red-400 border-red-trade',
}

function PresetPicker({ onSelect }: { onSelect: (preset: any) => void }) {
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const groups = ['Stocks', 'Crypto', 'Options', 'Momentum', 'Predictions']
  const presetList = Object.values(PRESETS)

  return (
    <div className="border border-[#30363d] rounded-lg p-4 space-y-3 bg-[#0d1117]">
      <div className="flex items-center gap-2">
        <Zap size={13} className="text-accent" />
        <span className="text-xs font-semibold text-gray-300">Load a preset</span>
      </div>
      {groups.map(group => (
        <div key={group}>
          <div className="text-[10px] text-gray-600 uppercase tracking-widest mb-1.5">{group}</div>
          <div className="flex gap-2">
            {presetList.filter(p => p.group === group).map(p => (
              <button
                key={p.key}
                onClick={() => { setActiveKey(p.key); onSelect(p) }}
                className={clsx(
                  'px-3 py-1.5 rounded border text-xs font-semibold transition-colors',
                  activeKey === p.key ? RISK_ACTIVE[p.label] : RISK_COLORS[p.label]
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      ))}
      {activeKey && (
        <div className="text-xs text-gray-500 pt-1 border-t border-[#21262d]">
          {PRESETS[activeKey]?.description}
        </div>
      )}
    </div>
  )
}

interface Account { id: string; label: string; class: string }
interface Decision { ts: string; symbol: string; action: string; qty?: number; reason: string; mode: string; order_id?: string }
interface MemoryEntry { ts: string; symbol?: string; action?: string; price?: number; note?: string }

function DecisionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    BUY:           'bg-green-trade/20 text-green-trade',
    SELL:          'bg-red-trade/20 text-red-trade',
    HOLD:          'bg-gray-700 text-gray-400',
    BUY_CALL:      'bg-green-trade/20 text-green-trade',
    BUY_PUT:       'bg-orange-500/20 text-orange-400',
    SELL_TO_CLOSE: 'bg-red-trade/20 text-red-trade',
    PASS:          'bg-gray-700 text-gray-400',
    BUY_YES:       'bg-green-trade/20 text-green-trade',
    BUY_NO:        'bg-red-trade/20 text-red-trade',
  }
  return <span className={clsx('text-xs px-1.5 py-0.5 rounded font-semibold', colors[action] ?? 'bg-gray-700 text-gray-400')}>{action}</span>
}

function StrategyMemory({ strategyId }: { strategyId: string }) {
  const [open, setOpen] = useState(false)
  const [entries, setEntries] = useState<MemoryEntry[]>([])

  const load = useCallback(async () => {
    const d: MemoryEntry[] = await fetch(`/api/engine/memory/${strategyId}`).then(r => r.json())
    setEntries(d)
  }, [strategyId])

  const clearMem = async () => {
    await fetch(`/api/engine/memory/${strategyId}`, { method: 'DELETE' })
    setEntries([])
  }

  useEffect(() => { if (open) load() }, [open, load])

  return (
    <div className="mt-2">
      <button onClick={() => setOpen(o => !o)} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300">
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Agent Memory <span className="text-gray-600">({entries.length || '?'} entries)</span>
        {open && <RefreshCw size={10} className="ml-1" onClick={e => { e.stopPropagation(); load() }} />}
      </button>
      {open && (
        <div className="mt-2">
          <div className="max-h-40 overflow-y-auto space-y-0.5 mb-2">
            {entries.length === 0 && <div className="text-xs text-gray-600 italic">No memory yet.</div>}
            {[...entries].reverse().map((e, i) => (
              <div key={i} className="flex gap-2 text-xs">
                <span className="text-gray-600 font-mono shrink-0">{e.ts?.slice(0,16).replace('T',' ')}</span>
                {e.symbol && <span className="text-gray-300 font-bold shrink-0">{e.symbol}</span>}
                {e.action && <DecisionBadge action={e.action} />}
                {e.price != null && e.price > 0 && <span className="text-gray-500">${e.price}</span>}
                {e.note && <span className="text-gray-500 truncate">{e.note}</span>}
              </div>
            ))}
          </div>
          <button onClick={clearMem} className="text-xs text-red-trade hover:underline">Clear memory</button>
        </div>
      )}
    </div>
  )
}

function StrategyDecisions({ strategyId }: { strategyId: string }) {
  const [open, setOpen] = useState(false)
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await fetch(`/api/engine/decisions?strategy_id=${strategyId}`).then(r => r.json())
      setDecisions(d[strategyId] || [])
    } catch { /* ignore */ }
    setLoading(false)
  }, [strategyId])

  useEffect(() => { if (open) load() }, [open, load])

  return (
    <div className="mt-3 border-t border-[#21262d] pt-2">
      <button onClick={() => { setOpen(o => !o); }} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300">
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Recent Decisions
        {open && <RefreshCw size={10} className={clsx('ml-1', loading && 'animate-spin')} onClick={e => { e.stopPropagation(); load() }} />}
      </button>
      {open && (
        <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
          {decisions.length === 0 && !loading && (
            <div className="text-xs text-gray-600 italic">No decisions yet — engine must run first.</div>
          )}
          {decisions.map((d, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className="text-gray-600 font-mono shrink-0">{new Date(d.ts).toLocaleTimeString()}</span>
              <span className="text-gray-300 font-bold shrink-0">{d.symbol}</span>
              <DecisionBadge action={d.action} />
              {d.qty != null && d.action !== 'HOLD' && <span className="text-gray-400">{d.qty} sh</span>}
              <span className="text-gray-500 truncate">{d.reason}</span>
              {d.mode === 'paper' && <span className="text-yellow-400 shrink-0">PAPER</span>}
              {d.order_id && <span className="text-green-trade shrink-0">✓ Filled</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Strategies({ engineStatus, refreshEngine }: any) {
  const [strategies, setStrategies] = useState<any[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<{ name: string; description: string; strategy_type: string; symbols: string; config: any; enabled: boolean }>(
    { name: '', description: '', strategy_type: 'sma_crossover', symbols: 'AAPL,TSLA', config: DEFAULT_SMA, enabled: false }
  )


  const load = () => fetch('/api/strategies').then(r => r.json()).then(setStrategies)
  useEffect(() => {
    load()
    fetch('/api/accounts').then(r => r.json()).then(setAccounts).catch(() => {})
  }, [])

  const save = async () => {
    const body = {
      ...form,
      symbols: form.symbols.split(',').map((s: string) => s.trim().toUpperCase()).filter(Boolean),
    }
    await fetch('/api/strategies', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    setShowForm(false)
    load()
  }

  const toggle = async (strat: any) => {
    await fetch(`/api/strategies/${strat.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !strat.enabled })
    })
    load()
  }

  const remove = async (id: string) => {
    await fetch(`/api/strategies/${id}`, { method: 'DELETE' })
    load()
  }

  const startEngine = async () => {
    await fetch('/api/engine/start', { method: 'POST' })
    refreshEngine()
  }

  const stopEngine = async () => {
    await fetch('/api/engine/stop', { method: 'POST' })
    refreshEngine()
  }

  const accountLabel = (id: string) => accounts.find(a => a.id === id)?.label ?? ''

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Strategies</h1>
        <div className="flex gap-3">
          <button onClick={engineStatus?.running ? stopEngine : startEngine}
            className={clsx('flex items-center gap-2 px-4 py-2 rounded text-sm font-semibold',
              engineStatus?.running ? 'bg-red-trade/20 text-red-trade hover:bg-red-trade/30' : 'bg-green-trade/20 text-green-trade hover:bg-green-trade/30')}>
            {engineStatus?.running ? <><Square size={14} /> Stop Engine</> : <><Play size={14} /> Start Engine</>}
          </button>
          <button onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 rounded text-sm font-semibold bg-accent/20 text-accent hover:bg-accent/30">
            <Plus size={14} /> New Strategy
          </button>
        </div>
      </div>

      {/* Engine status */}
      <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-4 flex items-center gap-4 text-sm">
        <span className={clsx('px-2 py-0.5 rounded text-xs font-semibold', engineStatus?.running ? 'bg-green-trade/20 text-green-trade' : 'bg-gray-700 text-gray-400')}>
          {engineStatus?.running ? 'RUNNING' : 'STOPPED'}
        </span>
        <span className="text-gray-400">Mode: <span className={clsx('font-semibold', engineStatus?.mode === 'live' ? 'text-red-trade' : 'text-accent')}>{engineStatus?.mode?.toUpperCase()}</span></span>
        {engineStatus?.stub_mode && <span className="text-yellow-400 text-xs">⚠ Stub mode — real credentials not configured</span>}
      </div>

      {/* Strategy list */}
      <div className="space-y-3">
        {strategies.map(s => {
          const acctId = s.config?.account_id
          return (
            <div key={s.id} className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1 flex-wrap">
                    <span className="font-semibold text-white">{s.name}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-[#21262d] text-gray-400">{s.strategy_type}</span>
                    <span className={clsx('text-xs px-2 py-0.5 rounded', s.enabled ? 'bg-green-trade/20 text-green-trade' : 'bg-gray-700 text-gray-500')}>
                      {s.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    {acctId && (
                      <span className="text-xs px-2 py-0.5 rounded bg-accent/10 text-accent">
                        {accountLabel(acctId) || acctId}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mb-2">{s.description}</div>
                  <div className="flex gap-2 flex-wrap">
                    {s.symbols?.map((sym: string) => (
                      <span key={sym} className="text-xs bg-[#21262d] text-gray-300 px-2 py-0.5 rounded">{sym}</span>
                    ))}
                    {(!s.symbols || s.symbols.length === 0) && (s.strategy_type === 'claude' || s.strategy_type === 'options' || s.strategy_type === 'momentum' || s.strategy_type === 'events') && (
                      <span className="text-xs text-accent">Auto market scan</span>
                    )}
                    {(!s.symbols || s.symbols.length === 0) && s.strategy_type === 'sma_crossover' && (
                      <span className="text-xs text-yellow-400">⚠ No symbols — add symbols to run</span>
                    )}
                  </div>
                  <div className="mt-2 text-xs text-gray-600 font-mono">
                    {Object.entries(s.config || {})
                      .filter(([k]) => k !== 'account_id')
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(' · ')}
                  </div>
                </div>
                <div className="flex gap-2 ml-4">
                  <button onClick={() => toggle(s)} className={clsx('p-2 rounded text-sm', s.enabled ? 'text-yellow-400 hover:bg-yellow-400/10' : 'text-green-trade hover:bg-green-trade/10')}>
                    {s.enabled ? <Square size={14} /> : <Play size={14} />}
                  </button>
                  <button onClick={() => remove(s.id)} className="p-2 rounded text-red-trade hover:bg-red-trade/10">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <StrategyDecisions strategyId={s.id} />
              {(s.strategy_type === 'claude' || s.strategy_type === 'options' || s.strategy_type === 'momentum' || s.strategy_type === 'events') && <StrategyMemory strategyId={s.id} />}
            </div>
          )
        })}
        {strategies.length === 0 && (
          <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-8 text-center text-gray-600">
            No strategies yet. Create one to get started.
          </div>
        )}
      </div>

      {/* New strategy modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-6 w-full max-w-lg space-y-4 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-bold text-white">New Strategy</h2>

            <PresetPicker onSelect={p => {
              setForm({
                name: p.name,
                description: p.description,
                strategy_type: p.strategy_type,
                symbols: (p.symbols || []).join(','),
                config: { ...p.config, account_id: '' },
                enabled: false,
              })
            }} />

            <div>
              <label className="text-xs text-gray-400 block mb-1">Name</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Description</label>
              <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Type</label>
              <select value={form.strategy_type} onChange={e => {
                const t = e.target.value
                setForm(f => ({ ...f, strategy_type: t, config: (t === 'claude' || t === 'options' || t === 'momentum' || t === 'events') ? DEFAULT_CLAUDE : DEFAULT_SMA }))
              }} className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
                <option value="sma_crossover">SMA Crossover</option>
                <option value="claude">AI Agent (Claude / Ollama)</option>
                <option value="options">Options Agent (calls &amp; puts)</option>
                <option value="momentum">Momentum Agent ($2–$20 small-caps)</option>
                <option value="events">Predictions Agent (Webull event markets)</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Trading Account</label>
              <select value={form.config.account_id || ''} onChange={e => setForm(f => ({ ...f, config: { ...f.config, account_id: e.target.value } }))}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
                <option value="">Use sidebar selection (default)</option>
                {accounts.map(a => <option key={a.id} value={a.id}>{a.label} ({a.class})</option>)}
              </select>
              <div className="text-xs text-gray-600 mt-1">Lock this strategy to a specific account regardless of sidebar selection.</div>
            </div>

            <div>
              <label className="text-xs text-gray-400 block mb-1">Symbols (comma separated)</label>
              <input value={form.symbols} onChange={e => setForm(f => ({ ...f, symbols: e.target.value }))}
                className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
            </div>

            {form.strategy_type === 'sma_crossover' && (
              <div className="grid grid-cols-3 gap-3">
                {[['fast_period', 'Fast Period'], ['slow_period', 'Slow Period'], ['quantity', 'Quantity']].map(([k, l]) => (
                  <div key={k}>
                    <label className="text-xs text-gray-400 block mb-1">{l}</label>
                    <input type="number" value={(form.config as any)[k]} onChange={e => setForm(f => ({ ...f, config: { ...f.config, [k]: Number(e.target.value) } }))}
                      className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
                  </div>
                ))}
              </div>
            )}

            {(form.strategy_type === 'claude' || form.strategy_type === 'options' || form.strategy_type === 'momentum' || form.strategy_type === 'events') && (
              <>
                <div className="grid grid-cols-3 gap-3">
                  {form.strategy_type === 'claude' && (
                    <div>
                      <label className="text-xs text-gray-400 block mb-1">Asset Class</label>
                      <select value={(form.config as any).asset_class ?? 'stocks'}
                        onChange={e => setForm(f => ({ ...f, config: { ...f.config, asset_class: e.target.value } }))}
                        className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
                        <option value="stocks">Stocks</option>
                        <option value="crypto">Crypto</option>
                        <option value="mixed">Mixed</option>
                      </select>
                    </div>
                  )}
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Scan Limit</label>
                    <input type="number" min={1} max={50} value={(form.config as any).scan_limit ?? 10}
                      onChange={e => setForm(f => ({ ...f, config: { ...f.config, scan_limit: Number(e.target.value) } }))}
                      className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
                    <div className="text-xs text-gray-600 mt-0.5">Top N symbols to scan</div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      {form.strategy_type === 'options' ? 'Max Premium ($)' : form.strategy_type === 'momentum' ? 'Max BP/Position ($)' : 'Max Position ($)'}
                    </label>
                    <input type="number" min={10} value={(form.config as any).max_position_usd ?? 500}
                      onChange={e => setForm(f => ({ ...f, config: { ...f.config, max_position_usd: Number(e.target.value) } }))}
                      className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
                    <div className="text-xs text-gray-600 mt-0.5">
                      {form.strategy_type === 'options' ? 'Max premium per trade' : form.strategy_type === 'momentum' ? 'Cap per position slot' : 'Max spend per trade'}
                    </div>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">System Prompt</label>
                  <textarea rows={4} value={(form.config as any).system_prompt}
                    onChange={e => setForm(f => ({ ...f, config: { ...f.config, system_prompt: e.target.value } }))}
                    className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent resize-none" />
                </div>
                {form.strategy_type === 'claude' && (
                  <div className="flex items-center gap-2">
                    <input type="checkbox" id="ext_hours" checked={!!(form.config as any).extended_hours}
                      onChange={e => setForm(f => ({ ...f, config: { ...f.config, extended_hours: e.target.checked } }))} />
                    <label htmlFor="ext_hours" className="text-sm text-gray-300">Extended hours trading (pre-market 4am, after-hours until 8pm ET)</label>
                  </div>
                )}
                <div className="text-xs text-gray-500 bg-[#0d1117] rounded p-2">
                  {form.strategy_type === 'options'
                    ? '💡 Leave Symbols empty to auto-scan top movers for option setups. Options only execute during regular market hours (9:30am–4pm ET). The agent fetches live option chains from Yahoo Finance and picks contracts based on your prompt.'
                    : form.strategy_type === 'momentum'
                    ? '💡 Momentum agent only runs during regular market hours (9:30am–4pm ET). It scans Yahoo Finance gainers + most-active, filters to $2–$20 stocks with 750k+ avg volume and 2x+ relative volume, then asks Claude to rank and execute the best setups in one batch call. Allocation scales automatically with position count.'
                    : form.strategy_type === 'events'
                    ? '💡 Predictions agent trades Webull\'s prediction market contracts. Each contract pays $1.00 if the event occurs and $0.00 if it doesn\'t — the price is the implied probability. Claude scans all open contracts, finds mispriced probabilities, and places BUY YES or BUY NO orders. Runs pre-market through after-hours.'
                    : '💡 Leave Symbols empty to auto-scan — stocks mode scans top gainers & most active, crypto mode scans the full crypto watchlist, mixed does both. Memory persists across restarts.'}
                </div>
              </>
            )}

            <div className="flex items-center gap-2">
              <input type="checkbox" id="enabled" checked={form.enabled} onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))} />
              <label htmlFor="enabled" className="text-sm text-gray-300">Enable immediately</label>
            </div>

            <div className="flex gap-3 pt-2">
              <button onClick={save} className="flex-1 py-2 bg-accent text-black rounded font-semibold text-sm hover:opacity-90">Create</button>
              <button onClick={() => setShowForm(false)} className="flex-1 py-2 bg-[#21262d] text-gray-300 rounded text-sm hover:bg-[#30363d]">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
