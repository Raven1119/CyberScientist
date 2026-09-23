import { useEffect, useRef, useState } from 'react'
import { AppProvider, useApp } from './app-context'
import type { Page } from './app-context'
import ResearchPage from './pages/ResearchPage'
import ExperiencePage from './pages/ExperiencePage'
import MailboxPage from './pages/MailboxPage'
import SettingsPage from './pages/SettingsPage'
import { PresentationProvider, usePresentation } from './design/presentation'
import { TargetCursor } from './design/TargetCursor'
import { enter } from './design/motion'

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
    <PresentationProvider><AppProvider><Shell /></AppProvider></PresentationProvider>
  )
}

function Shell() {
  const { page, setPage, demoMode } = useApp()
  const { theme, motion, reduced, focus, setPreference } = usePresentation()
  const view = useRef<HTMLDivElement>(null)

  // SPA 切页不保留上一页的滚动位置
  useEffect(() => {
    window.scrollTo(0, 0)
    if (view.current) return enter(view.current, 20)
  }, [page])

  return (
    <div className={`app${focus ? ' focus-view' : ''}`}>
      <a className="skip-link" href="#workspace">跳到工作区</a>
      <aside className="side" aria-label="工作区导航">
        <div className="brand">
          <div className="mark" aria-hidden="true">
            <svg viewBox="0 0 36 36" fill="none" stroke="currentColor" strokeWidth="1.2"><path d="M7 4h13M7 4v28h22V12M7 23L29 4M14 11v21M7 17h22M24 4h5v5" /><path d="M26 4h3v3" className="mark-accent" /></svg>
          </div>
          <div>
            <div className="brand-sub">RESEARCH<br /> SYSTEMS</div>
          </div>
        </div>
        <div className="workspace-name">CYBER<br />SCIENTIST<span>.</span></div>
        <p className="workspace-description">科学研究工作台</p>
        <div className="nav-label">WORKSPACE / 工作区</div>
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
            {demoMode && (
              <span className="badge demo">
                <span className="dot" aria-hidden="true" />
                演示模式
              </span>
            )}
            <div className="presentation-controls" role="group" aria-label="显示偏好">
              <button type="button" className="btn small" aria-pressed={motion && !reduced} disabled={reduced}
                title={reduced ? '跟随系统减少动态设置' : '开启或关闭界面动效'}
                onClick={() => setPreference('motion', !motion)}>{reduced ? '静态' : motion ? '动效 开' : '动效 关'}</button>
              <button type="button" className="btn small" aria-pressed={focus} title="收起导航以专注阅读；Esc 退出"
                onClick={() => setPreference('focus', !focus)}>{focus ? '退出专注' : '专注'}</button>
              <button type="button" className="btn icon-btn" aria-label={theme === 'paper' ? '切换夜间主题' : '切换日间主题'}
                title={theme === 'paper' ? '夜间 · 冷石墨' : '日间 · 纸色'} onClick={() => setPreference('theme', theme === 'paper' ? 'night' : 'paper')}>
                {theme === 'paper' ? <svg viewBox="0 0 20 20" fill="none" stroke="currentColor"><path d="M16 12A7 7 0 0 1 8 3a7 7 0 1 0 8 9Z" /></svg>
                  : <svg viewBox="0 0 20 20" fill="none" stroke="currentColor"><circle cx="10" cy="10" r="3.5" /><path d="M10 1v3m0 12v3M1 10h3m12 0h3M3.5 3.5l2 2m9 9l2 2m0-13-2 2m-9 9-2 2" /></svg>}
              </button>
            </div>
          </div>
        </header>
        <div className="content" id="workspace" tabIndex={-1}>
          <div ref={view} className="page-view">
          {page === 'research' && <ResearchPage />}
          {page === 'experience' && <ExperiencePage />}
          {page === 'mailbox' && <MailboxPage />}
          {page === 'settings' && <SettingsPage />}
          </div>
          <footer className="footer"><span>CyberScientist · {demoMode ? '演示工作区' : '研究工作区'}</span><BackendClock />
            <a href="/legal/research-interface-notices.txt" target="_blank" rel="noreferrer">界面来源与许可 ↗</a></footer>
        </div>
      </main>
      <TargetCursor />
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
