import Feed from './pages/Feed'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 bg-slate-950/90 backdrop-blur border-b border-slate-800">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between">
          <span className="text-lg font-semibold tracking-tight">Distill</span>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-4 py-6">
        <Feed />
      </main>
    </div>
  )
}
