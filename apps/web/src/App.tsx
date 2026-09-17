import { AppProvider, useApp } from './app-context'
import type { Page } from './app-context'
import { PairDialog } from './components'
import ResearchPage from './pages/ResearchPage'
import ExperiencePage from './pages/ExperiencePage'
import SettingsPage from './pages/SettingsPage'

const NAV_ITEMS: { page: Page; num: string; label: string }[] = [
  { page: 'research', num: '01', label: '研究工作台' },
  { page: 'experience', num: '02', label: '经验库' },
  { page: 'settings', num: '03', label: '连接与设置' },
]

const CRUMBS: Record<Page, string> = {
  research: '研究工作台',
  experience: '经验库',
  settings: '连接与设置',
}

function Shell() {
  const { page, setPage, demoMode, healthTime, paired, setPairDialogOpen } = useApp()

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="mark" aria-hidden="true">
            CS
          </div>
          <div>
            <div className="brand-name">CyberScientist</div>
            <div className="brand-sub">RESEARCH WORKSPACE</div>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.page}
              className={page === item.page ? 'active' : ''}
              aria-current={page === item.page ? 'page' : undefined}
              onClick={() => setPage(item.page)}
            >
              <span className="num" aria-hidden="true">
                {item.num}
              </span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="side-note">
          <strong>一轮实验，一份证据。</strong>
          大脑判断方向，Prime 自主执行。
          <br />
          科学计算保留远程来源。
          <br />
          <br />
          {!paired && (
            <button type="button" className="btn small ghost-light" onClick={() => setPairDialogOpen(true)}>
              输入配对码
            </button>
          )}
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="crumb">
            CyberScientist <b>/ {CRUMBS[page]}</b>
          </div>
          <div className="topbar-right">
            {healthTime && <span className="topbar-time">后端时间 {healthTime.slice(0, 19).replace('T', ' ')}</span>}
            {demoMode && (
              <span className="badge demo">
                <span className="dot" aria-hidden="true" />
                演示模式
              </span>
            )}
          </div>
        </header>
        <div className="content">
          {page === 'research' && <ResearchPage />}
          {page === 'experience' && <ExperiencePage />}
          {page === 'settings' && <SettingsPage />}
          <footer className="footer">CyberScientist · 生产前端 · 数据来自本地后端 API</footer>
        </div>
      </main>
      <PairDialog />
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
