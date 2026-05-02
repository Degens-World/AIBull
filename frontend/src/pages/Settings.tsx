import { useEffect, useState } from 'react'
import { Eye, EyeOff, Save, Send, RefreshCw, CheckCircle, XCircle, Loader } from 'lucide-react'
import clsx from 'clsx'

function StatusDot({ ok }: { ok?: boolean }) {
  if (ok == null) return <div className="w-2 h-2 rounded-full bg-gray-600" />
  return <div className={clsx('w-2 h-2 rounded-full', ok ? 'bg-green-trade' : 'bg-red-trade')} />
}

function CredentialField({
  label, field, value, onChange, placeholder, type = 'password', hint,
}: {
  label: string; field: string; value: string; onChange: (f: string, v: string) => void;
  placeholder?: string; type?: string; hint?: string;
}) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <label className="text-xs text-gray-400 block mb-1">{label}</label>
      <div className="relative">
        <input
          type={type === 'password' ? (show ? 'text' : 'password') : type}
          value={value}
          onChange={e => onChange(field, e.target.value)}
          placeholder={placeholder}
          className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white
                     focus:outline-none focus:border-accent pr-9 font-mono"
        />
        {type === 'password' && (
          <button type="button" onClick={() => setShow(s => !s)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
            {show ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
      {hint && <div className="text-xs text-gray-600 mt-0.5">{hint}</div>}
    </div>
  )
}

const BACKENDS = [
  { id: 'claude_cli', label: 'Claude CLI', desc: 'Uses your local Claude Code install — free, no API key' },
  { id: 'ollama',     label: 'Ollama',     desc: 'Local open-source models (llama3.2, mistral, etc.) — free, runs offline' },
  { id: 'anthropic',  label: 'Anthropic API', desc: 'Claude via API key — most capable, pay-per-use' },
]

export default function Settings() {
  const [apiSettings, setApiSettings] = useState<any>(null)
  const [creds, setCreds] = useState({
    webull_app_key: '', webull_app_secret: '', webull_trading_pin: '',
    webull_account_id: '', anthropic_api_key: '', trading_mode: 'paper',
    telegram_bot_token: '', telegram_chat_id: '',
    llm_backend: 'claude_cli', ollama_url: '', ollama_model: '',
  })
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [saveStatus, setSaveStatus] = useState('')
  const [alertMsg, setAlertMsg] = useState('')
  const [alertStatus, setAlertStatus] = useState('')

  const loadSettings = () =>
    fetch('/api/settings').then(r => r.json()).then(d => {
      setApiSettings(d)
      setCreds(prev => ({
        ...prev,
        trading_mode: d.trading_mode || 'paper',
        llm_backend:  d.llm_backend  || 'claude_cli',
        ollama_url:   d.ollama_url   || 'http://localhost:11434',
        ollama_model: d.ollama_model || 'llama3.2',
      }))
      if (d.ollama_running) {
        fetch('/api/ollama/models').then(r => r.json()).then(setOllamaModels).catch(() => {})
      }
    })

  useEffect(() => { loadSettings() }, [])

  const set = (field: string, value: string) =>
    setCreds(prev => ({ ...prev, [field]: value }))

  const save = async () => {
    setSaveStatus('Saving…')
    try {
      const res = await fetch('/api/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds),
      })
      const data = await res.json()
      setSaveStatus(`Saved (${data.updated_keys?.length ?? 0} keys updated)`)
      setCreds(prev => ({
        ...prev,
        webull_app_key: '', webull_app_secret: '', webull_trading_pin: '',
        anthropic_api_key: '', telegram_bot_token: '',
      }))
      await loadSettings()
    } catch { setSaveStatus('Error saving') }
    setTimeout(() => setSaveStatus(''), 4000)
  }

  const sendTestAlert = async () => {
    if (!alertMsg.trim()) return
    setAlertStatus('Sending…')
    try {
      const res = await fetch('/api/telegram/alert', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: alertMsg }),
      })
      if (res.ok) { setAlertStatus('Sent!'); setAlertMsg('') }
      else setAlertStatus('Error: bot not active yet')
    } catch { setAlertStatus('Failed') }
    setTimeout(() => setAlertStatus(''), 3000)
  }

  const activeBackend = creds.llm_backend

  return (
    <div className="p-6 space-y-5 max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <button onClick={loadSettings} className="text-gray-500 hover:text-gray-300"><RefreshCw size={14} /></button>
      </div>

      {/* Webull auth banner */}
      {apiSettings?.webull_auth_status === 'pending' && (
        <div className="bg-yellow-400/10 border border-yellow-400/30 rounded-lg px-4 py-3 text-sm text-yellow-400 flex items-start gap-3">
          <span className="text-lg leading-none">📱</span>
          <div>
            <div className="font-semibold">Webull Authorization Pending</div>
            <div className="text-xs mt-0.5 text-yellow-300/80">Open your Webull mobile app → Account → Security → API Access and approve the pending request. The app will connect automatically once approved.</div>
          </div>
        </div>
      )}
      {apiSettings?.webull_auth_status === 'authorized' && (
        <div className="bg-green-trade/10 border border-green-trade/30 rounded-lg px-4 py-3 text-sm text-green-trade">
          ✓ Webull API connected — showing live portfolio data
        </div>
      )}
      {apiSettings?.webull_auth_status === 'failed' && (
        <div className="bg-red-trade/10 border border-red-trade/30 rounded-lg px-4 py-3 text-sm text-red-trade">
          <div className="font-semibold">Webull connection failed</div>
          <div className="text-xs mt-0.5 opacity-80">{apiSettings.webull_auth_message}</div>
        </div>
      )}

      {/* Status overview */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Webull',   ok: apiSettings?.webull_auth_status === 'authorized' },
          { label: 'Telegram', ok: apiSettings?.has_telegram_token },
          { label: 'Claude CLI', ok: apiSettings?.claude_cli_available },
          { label: 'Ollama',   ok: apiSettings?.ollama_running },
        ].map(({ label, ok }) => (
          <div key={label} className="bg-[#161b22] border border-[#21262d] rounded-lg px-3 py-3 flex items-center gap-2">
            <StatusDot ok={ok} />
            <div>
              <div className="text-xs text-gray-300">{label}</div>
              <div className={clsx('text-xs', ok ? 'text-green-trade' : 'text-gray-600')}>
                {ok == null ? '…' : ok ? 'Ready' : 'Not set'}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* LLM Backend */}
      <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5 space-y-4">
        <div className="text-sm font-semibold text-white">AI Agent Backend</div>
        <div className="space-y-2">
          {BACKENDS.map(b => {
            const isActive = activeBackend === b.id
            const available =
              b.id === 'claude_cli' ? apiSettings?.claude_cli_available :
              b.id === 'ollama'     ? apiSettings?.ollama_running :
              b.id === 'anthropic'  ? apiSettings?.has_anthropic_key : false
            return (
              <button key={b.id} type="button" onClick={() => set('llm_backend', b.id)}
                className={clsx(
                  'w-full text-left px-4 py-3 rounded-lg border transition-colors',
                  isActive ? 'border-accent bg-accent/10' : 'border-[#30363d] bg-[#0d1117] hover:border-[#58a6ff]/40'
                )}>
                <div className="flex items-center gap-3">
                  <div className={clsx('w-3 h-3 rounded-full border-2',
                    isActive ? 'border-accent bg-accent' : 'border-gray-600')} />
                  <span className={clsx('text-sm font-semibold', isActive ? 'text-white' : 'text-gray-300')}>{b.label}</span>
                  <span className={clsx('ml-auto text-xs px-1.5 py-0.5 rounded',
                    available ? 'bg-green-trade/20 text-green-trade' : 'bg-gray-700 text-gray-500')}>
                    {available ? 'Available' : 'Not detected'}
                  </span>
                </div>
                <div className="text-xs text-gray-500 mt-1 ml-6">{b.desc}</div>
              </button>
            )
          })}
        </div>

        {/* Ollama sub-settings */}
        {activeBackend === 'ollama' && (
          <div className="mt-3 space-y-3 pl-4 border-l-2 border-accent/30">
            <div className="grid grid-cols-2 gap-3">
              <CredentialField label="Ollama URL" field="ollama_url" value={creds.ollama_url}
                onChange={set} type="text" placeholder="http://localhost:11434" />
              <div>
                <label className="text-xs text-gray-400 block mb-1">Model</label>
                {ollamaModels.length > 0 ? (
                  <select value={creds.ollama_model} onChange={e => set('ollama_model', e.target.value)}
                    className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
                    {ollamaModels.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                ) : (
                  <input value={creds.ollama_model} onChange={e => set('ollama_model', e.target.value)}
                    placeholder="llama3.2" type="text"
                    className="w-full bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent font-mono" />
                )}
              </div>
            </div>
            {!apiSettings?.ollama_running && (
              <div className="text-xs text-yellow-400 bg-yellow-400/10 border border-yellow-400/20 rounded px-3 py-2">
                Ollama not detected. Install from <span className="text-accent">ollama.com</span> then run <span className="font-mono text-accent">ollama pull llama3.2</span>
              </div>
            )}
          </div>
        )}

        {/* Anthropic API key (only shown when that backend selected) */}
        {activeBackend === 'anthropic' && (
          <div className="pl-4 border-l-2 border-accent/30">
            <CredentialField label="Anthropic API Key" field="anthropic_api_key" value={creds.anthropic_api_key}
              onChange={set} placeholder={apiSettings?.has_anthropic_key ? '••••••• (set)' : 'sk-ant-...'} />
          </div>
        )}

        {activeBackend === 'claude_cli' && !apiSettings?.claude_cli_available && (
          <div className="text-xs text-yellow-400 bg-yellow-400/10 border border-yellow-400/20 rounded px-3 py-2">
            Claude CLI not found on PATH. Make sure Claude Code is installed and <span className="font-mono text-accent">claude</span> is accessible.
          </div>
        )}
      </div>

      {/* Credentials form */}
      <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5 space-y-5">
        <div className="text-sm font-semibold text-white">API Keys</div>

        {/* Webull */}
        <div className="space-y-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider flex items-center gap-2">
            <StatusDot ok={apiSettings?.has_webull_key && apiSettings?.has_webull_secret} /> Webull
          </div>
          <div className="grid grid-cols-2 gap-3">
            <CredentialField label="App Key"    field="webull_app_key"    value={creds.webull_app_key}    onChange={set} placeholder={apiSettings?.has_webull_key ? '••••••• (set)' : 'Enter app key'} />
            <CredentialField label="App Secret" field="webull_app_secret" value={creds.webull_app_secret} onChange={set} placeholder={apiSettings?.has_webull_secret ? '••••••• (set)' : 'Enter app secret'} />
            <CredentialField label="Trading PIN" field="webull_trading_pin" value={creds.webull_trading_pin} onChange={set} placeholder="123456" />
            <CredentialField label="Account ID" field="webull_account_id" value={creds.webull_account_id} onChange={set} placeholder="Your account ID" type="text" />
          </div>
        </div>

        <div className="border-t border-[#21262d]" />

        {/* Telegram */}
        <div className="space-y-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider flex items-center gap-2">
            <StatusDot ok={apiSettings?.has_telegram_token} /> Telegram Bot
          </div>
          <div className="text-xs text-gray-500">
            Message <span className="text-accent">@BotFather</span> → <span className="text-accent">/newbot</span> → paste token below → Save → send <span className="text-accent">/start</span> to your bot
          </div>
          <div className="grid grid-cols-2 gap-3">
            <CredentialField label="Bot Token" field="telegram_bot_token" value={creds.telegram_bot_token}
              onChange={set} placeholder={apiSettings?.has_telegram_token ? '••••••• (set)' : '123456:ABC-...'} />
            <CredentialField label="Chat ID (auto-set on /start)" field="telegram_chat_id" value={creds.telegram_chat_id}
              onChange={set} placeholder={apiSettings?.telegram_chat_id ? String(apiSettings.telegram_chat_id) : 'Leave blank'} type="text" />
          </div>
        </div>

        <div className="border-t border-[#21262d]" />

        {/* Trading mode */}
        <div className="space-y-2">
          <div className="text-xs text-gray-500 uppercase tracking-wider">Trading Mode</div>
          <div className="flex gap-3">
            {['paper', 'live'].map(mode => (
              <button key={mode} type="button" onClick={() => set('trading_mode', mode)}
                className={clsx('flex-1 py-2 rounded text-sm font-semibold transition-colors border',
                  creds.trading_mode === mode
                    ? mode === 'live' ? 'bg-red-trade/30 text-red-trade border-red-trade/50'
                      : 'bg-accent/20 text-accent border-accent/40'
                    : 'bg-[#21262d] text-gray-400 hover:text-gray-200 border-transparent'
                )}>
                {mode === 'live' ? '⚡ Live Trading' : '📄 Paper Trading'}
              </button>
            ))}
          </div>
          {creds.trading_mode === 'live' && (
            <div className="text-xs text-red-trade bg-red-trade/10 border border-red-trade/20 rounded px-3 py-2">
              ⚠ Live trading uses real money. Thoroughly test strategies in paper mode first.
            </div>
          )}
        </div>

        <button onClick={save}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-accent text-black rounded font-semibold text-sm hover:opacity-90">
          <Save size={14} /> Save Settings
        </button>
        {saveStatus && <div className="text-xs text-center text-accent">{saveStatus}</div>}
      </div>

      {/* Telegram test */}
      {apiSettings?.telegram_bot_active && (
        <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-5 space-y-3">
          <div className="text-sm font-semibold text-white flex items-center gap-2">
            Telegram Test <span className="text-xs px-1.5 py-0.5 rounded bg-green-trade/20 text-green-trade">Active</span>
          </div>
          <div className="flex gap-2">
            <input value={alertMsg} onChange={e => setAlertMsg(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendTestAlert()}
              placeholder="Send a test message…"
              className="flex-1 bg-[#0d1117] border border-[#30363d] rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-accent" />
            <button onClick={sendTestAlert}
              className="flex items-center gap-1.5 px-3 py-2 bg-accent/20 text-accent rounded hover:bg-accent/30 text-sm">
              <Send size={13} /> Send
            </button>
          </div>
          {alertStatus && <div className="text-xs text-accent">{alertStatus}</div>}
          <div className="text-xs text-gray-600">
            /account · /positions · /quote AAPL · /buy AAPL 10 · /sell AAPL 5 · /engine start|stop · /logs
          </div>
        </div>
      )}

      {/* About */}
      <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-4">
        <div className="text-xs text-gray-600 space-y-0.5">
          <div>AIBull · FastAPI + Webull OpenAPI SDK · React · SQLite</div>
          <div>Credentials stored in <span className="text-gray-400">.env</span> (local only, never transmitted)</div>
        </div>
      </div>
    </div>
  )
}
