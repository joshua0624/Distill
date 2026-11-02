import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Triage from './pages/Triage'
import Channels from './pages/Channels'

const NAV = [
  { to: '/', label: 'Home', icon: 'M4 10.5 12 4l8 6.5V20h-5v-6H9v6H4z' },
  { to: '/triage', label: 'Triage', icon: 'M4 6h16M4 12h10M4 18h6M17 14l3 3-3 3' },
  { to: '/channels', label: 'Channels', icon: 'M4 5h16v11H4zM8 20h8M12 16v4' },
]

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="size-6 shrink-0" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  )
}

export default function App() {
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-20 flex h-14 items-center gap-2 bg-bg px-4">
        <a href="/" className="flex items-center gap-1.5 text-lg font-semibold tracking-tight">
          <img src="/favicon.svg" alt="" className="size-7" />
          Distill
        </a>
      </header>

      <div className="flex flex-1">
        <nav className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 flex-col gap-1 px-3 py-2 md:flex">
          {NAV.map(n => (
            <NavLink key={n.to} to={n.to} end
              className={({ isActive }) =>
                `flex items-center gap-5 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-surface font-medium' : 'hover:bg-surface'}`}>
              <Icon d={n.icon} />
              {n.label}
            </NavLink>
          ))}
        </nav>

        <main className="min-w-0 flex-1 px-4 pb-24 md:px-6 md:pb-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/triage" element={<Triage />} />
            <Route path="/channels" element={<Channels />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-bg pb-[env(safe-area-inset-bottom)] md:hidden">
        {NAV.map(n => (
          <NavLink key={n.to} to={n.to} end
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] ${isActive ? 'text-fg' : 'text-muted'}`}>
            <Icon d={n.icon} />
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
