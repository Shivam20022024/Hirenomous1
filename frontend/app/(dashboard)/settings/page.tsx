'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { User, Building, Mail, Shield, Bell, Key, LogOut } from 'lucide-react';
import { PageHeader } from '@/components/page-header';

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<'profile' | 'organization' | 'security'>('profile');

  return (
    <div className="mx-auto max-w-[1240px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <PageHeader eyebrow="Account" title="Settings" description="Manage your account settings and preferences." />

      <div className="flex flex-col md:flex-row gap-8">
        <aside className="w-full md:w-64 shrink-0 space-y-1">
          <button 
            onClick={() => setActiveTab('profile')}
            className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${activeTab === 'profile' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
          >
            <User size={18} /> Profile
          </button>
          <button 
            onClick={() => setActiveTab('organization')}
            className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${activeTab === 'organization' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
          >
            <Building size={18} /> Organization
          </button>
          <button 
            onClick={() => setActiveTab('security')}
            className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${activeTab === 'security' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
          >
            <Shield size={18} /> Security
          </button>
          <hr className="my-4 border-border" />
          <button 
            onClick={logout}
            className="w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-destructive transition-colors hover:bg-destructive/10"
          >
            <LogOut size={18} /> Log out
          </button>
        </aside>

        <div className="flex-1 space-y-6">
          {activeTab === 'profile' && (
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="border-b border-border px-6 py-5 bg-muted/30">
                <h2 className="text-lg font-bold">Profile Details</h2>
                <p className="text-base font-semibold text-foreground">Your personal account information.</p>
              </div>
              <div className="p-6 space-y-6">
                <div className="flex items-center gap-6">
                  <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 text-3xl font-bold text-primary">
                    {user?.name?.charAt(0).toUpperCase() || 'U'}
                  </div>
                  <div>
                    <button className="rounded-xl border border-border bg-background px-4 py-2 text-sm font-semibold hover:bg-muted">Change Avatar</button>
                  </div>
                </div>
                
                <div className="grid gap-6 sm:grid-cols-2">
                  <div>
                    <label className="text-sm font-medium">Full Name</label>
                    <input disabled value={user?.name || ''} className="mt-1 w-full rounded-xl border border-border bg-muted px-4 py-3 text-sm opacity-70" />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Email Address</label>
                    <div className="relative mt-1">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
                      <input disabled value={user?.email || ''} className="w-full rounded-xl border border-border bg-muted pl-10 pr-4 py-3 text-sm opacity-70" />
                    </div>
                  </div>
                  <div>
                    <label className="text-sm font-medium">Role</label>
                    <input disabled value={user?.role || 'user'} className="mt-1 w-full rounded-xl border border-border bg-muted px-4 py-3 text-sm opacity-70 capitalize" />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'organization' && (
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="border-b border-border px-6 py-5 bg-muted/30">
                <h2 className="text-lg font-bold">Organization Details</h2>
                <p className="text-base font-semibold text-foreground">Information about your workspace.</p>
              </div>
              <div className="p-6 space-y-6">
                <div className="grid gap-6 sm:grid-cols-2">
                  <div>
                    <label className="text-sm font-medium">Organization Name</label>
                    <div className="relative mt-1">
                      <Building className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
                      <input disabled value={user?.organization_name || 'My Organization'} className="w-full rounded-xl border border-border bg-muted pl-10 pr-4 py-3 text-sm opacity-70" />
                    </div>
                  </div>
                  <div>
                    <label className="text-sm font-medium">Organization ID</label>
                    <input disabled value={user?.org_id || user?.organization_id || ''} className="mt-1 w-full rounded-xl border border-border bg-muted px-4 py-3 text-sm opacity-70" />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'security' && (
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="border-b border-border px-6 py-5 bg-muted/30">
                <h2 className="text-lg font-bold">Security</h2>
                <p className="text-base font-semibold text-foreground">Manage your password and security preferences.</p>
              </div>
              <div className="p-6 space-y-6">
                <div className="flex items-center justify-between border-b border-border pb-6">
                  <div>
                    <h3 className="font-semibold flex items-center gap-2"><Key size={16} /> Password</h3>
                    <p className="text-base font-semibold text-foreground mt-1">Change your password to keep your account secure.</p>
                  </div>
                  <button className="rounded-xl border border-border bg-background px-4 py-2 text-sm font-semibold hover:bg-muted">Change Password</button>
                </div>
                
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold flex items-center gap-2"><Bell size={16} /> Two-Factor Authentication</h3>
                    <p className="text-base font-semibold text-foreground mt-1">Add an extra layer of security to your account.</p>
                  </div>
                  <button className="rounded-xl border border-border bg-background px-4 py-2 text-sm font-semibold hover:bg-muted">Enable 2FA</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
