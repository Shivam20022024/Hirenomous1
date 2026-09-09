'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { ThemeToggle } from '@/components/theme-toggle';
import {
  BarChart3,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Menu,
  X,
  UsersRound,
  FileText,
  Bot,
  Phone,
  Briefcase,
  Settings,
  ClipboardCheck
} from 'lucide-react';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: BarChart3 },
  { name: 'Jobs', href: '/jobs', icon: Briefcase },
  { name: 'Candidates', href: '/candidates', icon: UsersRound },
  { name: 'Candidate Profiles', href: '/resumes', icon: FileText },
  { name: 'AI Hiring Assistant', href: '/ai-recruiter', icon: Bot },
  { name: 'Calling Campaigns', href: '/campaigns', icon: Phone },
  { name: 'AI Interviews', href: '/interviews', icon: ClipboardCheck },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const [dropdownOpen, setDropdownOpen] = useState(false);

  return (
    <div className="fixed inset-0 flex overflow-hidden bg-background">
      {/* Sidebar */}
      <aside
        className={`app-surface ${menuOpen ? 'flex' : 'hidden'} fixed inset-y-0 left-0 z-40 w-64 flex-col border-r border-sidebar-border lg:relative lg:flex ${collapsed ? 'lg:w-[76px]' : 'lg:w-64'}`}
      >
        <div className={`flex h-20 items-center border-b border-sidebar-border ${collapsed ? 'lg:justify-center lg:px-2' : 'justify-between px-6'}`}>
          <div className="flex items-center gap-3">
            <div className="brand-mark !h-9 !w-9 shrink-0 text-lg">H</div>
            <span className={`text-lg font-bold tracking-tight text-sidebar-foreground ${collapsed ? 'lg:hidden' : ''}`}>Hireonomous</span>
          </div>
          <button onClick={() => setMenuOpen(false)} className="rounded-lg p-2 text-muted-foreground hover:bg-muted lg:hidden" aria-label="Close navigation">
            <X size={18}/>
          </button>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="hidden lg:absolute lg:-right-3 lg:top-7 lg:flex lg:h-7 lg:w-7 lg:items-center lg:justify-center lg:rounded-full lg:border lg:border-sidebar-border lg:bg-card lg:text-muted-foreground lg:shadow-sm lg:transition-colors lg:hover:bg-muted lg:hover:text-foreground"
            aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          >
            {collapsed ? <ChevronsRight size={15}/> : <ChevronsLeft size={15}/>}
          </button>
        </div>
        <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 py-7" aria-label="Main navigation">
          {navigation.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.name}
                href={item.href}
                onClick={() => setCollapsed(false)}
                title={collapsed ? item.name : undefined}
                className={`flex w-full items-center gap-3 rounded-lg py-2.5 text-sm font-semibold transition-colors ${collapsed ? 'lg:justify-center lg:px-0' : 'px-3'} ${isActive ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
              >
                <item.icon size={17} strokeWidth={2.25} className="shrink-0" />
                <span className={collapsed ? 'lg:sr-only' : ''}>{item.name}</span>
              </Link>
            );
          })}
        </nav>
        <div className={`border-t border-sidebar-border p-5 ${collapsed ? 'lg:p-3' : ''}`}>
          <div className={`flex items-center gap-3 relative ${collapsed ? 'lg:flex-col lg:gap-2' : ''}`}>
            <div className="avatar avatar-blue shrink-0">
              {user?.name?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className={`min-w-0 flex-1 ${collapsed ? 'lg:hidden' : ''}`}>
              <p className="truncate text-sm font-semibold text-sidebar-foreground">{user?.name || 'User'}</p>
              <p className="truncate text-xs text-muted-foreground">{user?.email || 'user@example.com'}</p>
            </div>
            <button onClick={() => setDropdownOpen(!dropdownOpen)} aria-label="Account menu">
               <ChevronDown className={`text-muted-foreground hover:text-foreground cursor-pointer ${collapsed ? '' : 'ml-auto'}`} size={16}/>
            </button>

            {dropdownOpen && (
              <div className="absolute bottom-12 right-0 w-48 rounded-lg border border-border bg-card p-1 shadow-lg">
                <button onClick={logout} className="w-full rounded-md px-3 py-2 text-left text-sm text-destructive hover:bg-destructive/10">
                  Log out
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {menuOpen && <button onClick={() => setMenuOpen(false)} className="fixed inset-0 z-30 bg-foreground/20 lg:hidden" aria-label="Close navigation overlay"/>}

      <div className="min-w-0 flex-1 flex flex-col">
        {/* Header */}
        <header className="app-surface sticky top-0 z-20 flex h-20 items-center justify-between border-b border-border px-5 backdrop-blur lg:px-10">
          <button onClick={() => setMenuOpen(true)} className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted lg:hidden" aria-label="Open navigation">
            <Menu size={20}/>
          </button>
          <div className="hidden lg:block"/>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-foreground">{user?.name || 'User'}</p>
              <p className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">{user?.organization_name || 'Admin'}</p>
            </div>
            <div className="avatar avatar-blue !h-9 !w-9">
               {user?.name?.charAt(0).toUpperCase() || 'U'}
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="app-surface min-h-0 flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
