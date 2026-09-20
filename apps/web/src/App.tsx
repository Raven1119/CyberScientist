import { useEffect, useState } from 'react'
import { AppProvider, useApp } from './app-context'
import type { Page } from './app-context'
import ResearchPage from './pages/ResearchPage'
import ExperiencePage from './pages/ExperiencePage'
import MailboxPage from './pages/MailboxPage'
import SettingsPage from './pages/SettingsPage'

const NAV_ITEMS: { page: Page; num: string; label: string }[] = [
  { page: 'research', num: '01', label: '研究工作台' },
  { page: 'experience', num: '02', label: '经验库' },
  { page: 'mailbox', num: '03', label: '邮箱与提交' },
  { page: 'settings', num: '04', label: '连接与设置' },
]

const CRUMBS: Record<Page, string> = {
  research: '研究工作台',
  experience: '经验库',
  mailbox: '邮箱与提交',
  settings: '连接与设置',
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}

function Shell() {
  const { page, setPage, demoMode } = useApp()

  // SPA 切页不保留上一页的滚动位置
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [page])

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
          大脑判断方向，执行器自主执行。
          <br />
          科学计算保留远程来源。
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="crumb">
            CyberScientist <b>/ {CRUMBS[page]}</b>
          </div>
          <div className="topbar-right">
            <BackendClock />
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
          {page === 'mailbox' && <MailboxPage />}
          {page === 'settings' && <SettingsPage />}
          <footer className="footer">CyberScientist · 生产前端 · 数据来自本地后端 API</footer>
        </div>
      </main>
    </div>
  )
}

/** 顶栏后端时钟：以最近健康检查的后端时间为基准，按本地时区每秒走动。 */
function BackendClock() {
  const { healthTime } = useApp()
  const [, setTick] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => setTick((n) => n + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])

  if (!healthTime) return null
  const base = Date.parse(healthTime.serverTime)
  if (Number.isNaN(base)) return null
  const shown = new Date(base + (Date.now() - healthTime.receivedAt))
  return (
    <span className="topbar-time" title="后端时间，按本地时区显示">
      后端时间 {shown.toLocaleString('zh-CN', { hour12: false })}（本地时区）
    </span>
  )
}
