'use client';

import Link from 'next/link';
import {
  ArrowRight,
  Sparkles,
  BarChart3,
  Headset,
  Lock,
  Smartphone,
  Wand2,
  ShieldCheck,
  Zap,
  CheckCircle2,
  Users,
  FileSearch,
  Mic,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { Reveal } from '@/components/reveal';
import { BrandLogo } from '@/components/brand-logo';

function FeatureCard({ children }: { children: React.ReactNode }) {
  return (
    <div aria-hidden="true" className="flex h-56 flex-col justify-between rounded-xl border border-border bg-card p-6 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
      {children}
    </div>
  );
}

function ScoreDistribution() {
  const bands = [
    { label: '90–100%', pct: 92 },
    { label: '75–89%', pct: 68 },
    { label: '60–74%', pct: 42 },
    { label: 'Below 60%', pct: 18 },
  ];
  return (
    <FeatureCard>
      <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Match score distribution</p>
      <div className="space-y-2.5">
        {bands.map((b) => (
          <div key={b.label} className="flex items-center gap-3">
            <span className="w-16 shrink-0 text-xs font-semibold text-muted-foreground">{b.label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${b.pct}%` }} />
            </div>
          </div>
        ))}
      </div>
    </FeatureCard>
  );
}

function InterviewScore() {
  const dims = [
    { label: 'Technical', pct: 88 },
    { label: 'Communication', pct: 91 },
    { label: 'Problem solving', pct: 82 },
  ];
  return (
    <FeatureCard>
      <div className="flex items-center gap-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-4 border-primary/25">
          <span className="font-mono text-lg font-bold text-primary">87</span>
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Avg. interview score</p>
          <span className="mt-1.5 inline-block rounded-full bg-success/15 px-2 py-0.5 text-[11px] font-bold text-success">Strong match</span>
        </div>
      </div>
      <div className="space-y-2">
        {dims.map((d) => (
          <div key={d.label} className="flex items-center gap-3">
            <span className="w-28 shrink-0 text-xs font-semibold text-muted-foreground">{d.label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${d.pct}%` }} />
            </div>
          </div>
        ))}
      </div>
    </FeatureCard>
  );
}

function CampaignBreakdown() {
  const segments = [
    { label: 'Completed', pct: 54, cls: 'bg-success' },
    { label: 'Calling', pct: 21, cls: 'bg-warning' },
    { label: 'Queued', pct: 25, cls: 'bg-muted-foreground/30' },
  ];
  return (
    <FeatureCard>
      <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Call outcomes this week</p>
      <div>
        <div className="flex h-3 overflow-hidden rounded-full">
          {segments.map((s) => (
            <div key={s.label} className={`h-full ${s.cls}`} style={{ width: `${s.pct}%` }} />
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
          {segments.map((s) => (
            <span key={s.label} className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <span className={`h-2 w-2 rounded-full ${s.cls}`} /> {s.label}
              <span className="font-mono tabular-nums text-muted-foreground">{s.pct}%</span>
            </span>
          ))}
        </div>
      </div>
    </FeatureCard>
  );
}

function ConversionTrend() {
  const months = [
    { label: 'Jun', h: 45 },
    { label: 'Jul', h: 55 },
    { label: 'Aug', h: 50 },
    { label: 'Sep', h: 70 },
    { label: 'Oct', h: 65 },
    { label: 'Nov', h: 85 },
  ];
  return (
    <FeatureCard>
      <div className="flex items-center justify-between">
        <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Applied → hired conversion</p>
        <span className="font-mono text-sm font-bold text-success">+18%</span>
      </div>
      <div>
        <div className="grid h-20 items-end gap-2" style={{ gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` }}>
          {months.map((m) => (
            <div key={m.label} className="rounded-t-md bg-primary/70" style={{ height: `${m.h}%` }} />
          ))}
        </div>
        <div className="mt-1.5 grid gap-2" style={{ gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` }}>
          {months.map((m) => (
            <span key={m.label} className="text-center text-[10px] font-semibold text-muted-foreground">{m.label}</span>
          ))}
        </div>
      </div>
    </FeatureCard>
  );
}

const FEATURES = [
  {
    eyebrow: 'Source & screen',
    eyebrowColor: 'text-foreground',
    title: 'Find and rank the right resumes',
    desc: 'Upload resumes one at a time or by the hundred. The AI parses, scores against the job, and ranks every candidate automatically.',
    Visual: ScoreDistribution,
  },
  {
    eyebrow: 'Evaluate candidates',
    eyebrowColor: 'text-primary',
    title: 'Run structured AI interviews',
    desc: 'Voice screening calls and full video interviews, scored on the same rubric every time, with a transcript and recommendation for every candidate.',
    Visual: InterviewScore,
  },
  {
    eyebrow: 'Automate outreach',
    eyebrowColor: 'text-accent-foreground',
    title: 'Call every shortlisted candidate',
    desc: 'Queue AI screening calls for an entire shortlist at once, track status live, and sync results back into the pipeline without lifting a phone.',
    Visual: CampaignBreakdown,
  },
  {
    eyebrow: 'Decide with data',
    eyebrowColor: 'text-success',
    title: 'See the whole funnel at a glance',
    desc: 'From applied to hired, watch conversion by role and stage so you know exactly where candidates are getting stuck.',
    Visual: ConversionTrend,
  },
];

const PIPELINE = [
  { label: 'Applied', count: 1240, width: 100, icon: Users },
  { label: 'AI screened', count: 612, width: 68, icon: FileSearch },
  { label: 'Interviewed', count: 148, width: 32, icon: Mic },
  { label: 'Hired', count: 32, width: 14, icon: CheckCircle2 },
];

function PipelineInfographic() {
  return (
    <div className="relative mx-auto w-full max-w-md rounded-2xl border border-primary-foreground/15 bg-primary-foreground/10 p-6 backdrop-blur-sm sm:p-7">
      <p className="text-xs font-bold uppercase tracking-wide text-primary-foreground/60">This week's pipeline</p>
      <div className="mt-5 space-y-4">
        {PIPELINE.map((stage) => (
          <div key={stage.label}>
            <div className="flex items-center gap-2.5">
              <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-warning text-warning-foreground">
                <stage.icon size={14} />
              </span>
              <span className="flex-1 text-sm font-semibold text-primary-foreground">{stage.label}</span>
              <span className="font-mono text-base font-bold tabular-nums text-primary-foreground">{stage.count.toLocaleString()}</span>
            </div>
            <div className="mt-2 ml-[38px] h-2 overflow-hidden rounded-full bg-primary-foreground/15">
              <div className="h-full rounded-full bg-warning" style={{ width: `${stage.width}%` }} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-5 flex items-center justify-between border-t border-primary-foreground/15 pt-4 text-xs font-semibold text-primary-foreground/70">
        <span>Conversion, applied to hired</span>
        <span className="font-mono tabular-nums text-warning">2.6%</span>
      </div>
    </div>
  );
}

const REASONS = [
  { icon: Wand2, title: 'AI-generated screening questions', desc: 'Every job gets a tailored question set the AI writes and scores against automatically.' },
  { icon: Headset, title: 'Human intervention when needed', desc: 'Recruiters keep the final call on every decision the AI recommends.' },
  { icon: ShieldCheck, title: 'Secure by default', desc: 'Candidate data stays scoped to your organization, with role-based access built in.' },
  { icon: Smartphone, title: 'Works anywhere', desc: 'Review candidates, reports, and recordings from any device.' },
  { icon: Zap, title: 'Minutes, not weeks', desc: 'Go from resume upload to a scored, ranked shortlist the same day.' },
  { icon: CheckCircle2, title: 'One record per candidate', desc: 'Resume, calls, interview, and decision all live on a single candidate timeline.' },
];

export default function RootPage() {
  const { user } = useAuth();
  const primaryHref = user ? '/dashboard' : '/login';

  return (
    <div className="theme-force-light min-h-screen bg-background">
      {/* Announcement strip */}
      <div className="bg-warning-surface/60 px-4 py-2 text-center text-xs font-semibold text-foreground">
        New: the AI Hiring Assistant now writes tailored screening questions for every job.{' '}
        <Link href={primaryHref} className="text-primary underline underline-offset-2">See how it works</Link>
      </div>

      {/* Hero (nav lives inside this band) */}
      <section className="relative overflow-hidden bg-primary">
        <span aria-hidden="true" className="pointer-events-none absolute left-[8%] top-16 h-2 w-2 rounded-full bg-warning" />
        <span aria-hidden="true" className="pointer-events-none absolute left-[3%] bottom-24 h-3 w-3 rotate-45 bg-accent" />
        <span aria-hidden="true" className="pointer-events-none absolute right-[6%] bottom-20 h-2 w-2 rounded-full bg-warning-surface" />

        <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <BrandLogo className="h-8 w-8 shrink-0" />
            <span className="text-base font-bold tracking-tight text-primary-foreground">Hireonomous</span>
          </div>
          <div className="flex items-center gap-2">
            <Link href={user ? '/dashboard' : '/login'} className="hidden text-sm font-semibold text-primary-foreground/90 hover:text-primary-foreground sm:inline">
              {user ? 'Dashboard' : 'Log in'}
            </Link>
            <a
              href="https://novalantis.com/contact-us/"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full bg-primary-foreground px-4 py-2 text-sm font-bold text-primary shadow-sm"
            >
              Contact us <ArrowRight size={14} />
            </a>
          </div>
        </header>

        <div className="mx-auto grid max-w-7xl gap-10 px-4 pb-20 pt-8 sm:px-6 lg:grid-cols-2 lg:items-center lg:px-8 lg:pb-28">
          <div className="max-w-xl">
            <Reveal>
              <h1 className="text-4xl font-bold leading-[1.1] tracking-tight text-primary-foreground sm:text-5xl">
                Find the Right Talent in Minutes, Not Weeks
              </h1>
            </Reveal>
            <Reveal delay={100}>
              <p className="mt-5 text-base leading-relaxed text-primary-foreground/85 sm:text-lg">
                Hireonomous screens resumes, runs AI voice and video interviews, and scores every candidate the same way, so your team spends time on decisions, not data entry.
              </p>
            </Reveal>
            <Reveal delay={200}>
              <div className="mt-8 flex flex-wrap items-center gap-5">
                <Link href={primaryHref} className="inline-flex items-center gap-2 rounded-full bg-warning px-7 py-3.5 text-sm font-bold text-warning-foreground shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md">
                  Get started <ArrowRight size={16} />
                </Link>
              </div>
            </Reveal>
          </div>

          <Reveal delay={150}>
            <PipelineInfographic />
          </Reveal>
        </div>
      </section>

      {/* Feature grid */}
      <section id="product" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <Reveal className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            Manage your entire pipeline, from first resume to final decision
          </h2>
        </Reveal>

        <div className="grid items-start gap-x-10 gap-y-16 sm:grid-cols-2">
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={i * 100} className="flex flex-col">
              <div className="mb-5">
                <f.Visual />
              </div>
              <p className={`text-xs font-bold uppercase tracking-wide ${f.eyebrowColor}`}>{f.eyebrow}</p>
              <h3 className="mt-1.5 text-lg font-bold text-foreground">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.desc}</p>
              <Link href={primaryHref} className="group mt-3 inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-primary hover:underline">
                See it in the dashboard <span className="transition-transform group-hover:translate-x-1">→</span>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Capability / stats band */}
      <section id="workflow" className="relative overflow-hidden bg-ink py-20 text-ink-foreground">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <Reveal className="max-w-2xl">
            <span className="eyebrow !text-warning">Built for speed</span>
            <h2 className="mt-3 text-3xl font-bold tracking-tight text-ink-foreground sm:text-4xl">
              Where hiring bottlenecks disappear
            </h2>
            <p className="mt-4 text-base leading-relaxed text-ink-foreground/70">
              Every stage of the pipeline, from screening to the final interview report, runs on the same consistent AI evaluation, so nothing depends on who happened to review it.
            </p>
          </Reveal>

          <div className="mt-12 grid grid-cols-1 gap-8 border-t border-ink-foreground/15 pt-10 sm:grid-cols-3">
            {[
              { value: '85%', label: 'Reduction in unconscious bias vs. manual review' },
              { value: '10x', label: 'Faster from resume upload to shortlist' },
              { value: '24/7', label: 'AI screening and interviewing, no scheduling required' },
            ].map((stat, i) => (
              <Reveal key={stat.label} delay={i * 100}>
                <div className="font-mono text-4xl font-bold text-warning">{stat.value}</div>
                <div className="mt-1.5 text-sm font-semibold text-ink-foreground/70">{stat.label}</div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Reasons grid */}
      <section id="why" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8">
        <Reveal className="mx-auto mb-14 max-w-xl text-center">
          <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">More reasons teams choose Hireonomous</h2>
        </Reveal>
        <div className="grid grid-cols-1 gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {REASONS.map((r, i) => (
            <Reveal key={r.title} delay={(i % 3) * 100} className="group flex flex-col items-center gap-3 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/20 text-accent-foreground transition-transform duration-300 group-hover:scale-110">
                <r.icon size={20} strokeWidth={1.75} />
              </span>
              <h4 className="text-sm font-bold text-foreground">{r.title}</h4>
              <p className="text-sm font-bold leading-relaxed text-foreground">{r.desc}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="mx-auto max-w-4xl px-4 pb-20 text-center sm:px-6 lg:px-8">
        <Reveal className="rounded-2xl border border-border bg-card px-6 py-14 shadow-sm transition-shadow duration-300 hover:shadow-lg sm:px-12">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Sparkles size={20} />
          </span>
          <h2 className="mt-5 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">Let's fix your hiring pipeline</h2>
          <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            Post a job, upload resumes, and let the AI screen and interview your candidates the same day.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href={primaryHref} className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-8 py-3.5 text-sm font-bold text-primary-foreground shadow-sm transition-all hover:-translate-y-0.5 hover:bg-primary/90 hover:shadow-md sm:w-auto">
              Get started <ArrowRight size={16} />
            </Link>
            <a href="https://novalantis.com/contact-us/" className="inline-flex w-full items-center justify-center rounded-full border border-border px-8 py-3.5 text-sm font-bold text-foreground transition-all hover:-translate-y-0.5 hover:bg-muted sm:w-auto">
              Contact sales
            </a>
          </div>
        </Reveal>
      </section>

      {/* Footer */}
      <footer className="bg-ink pt-14 pb-8 text-ink-foreground/70">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 gap-8 border-b border-ink-foreground/15 pb-10 sm:grid-cols-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-ink-foreground/50">Product</p>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li><a href="#product" className="hover:text-ink-foreground">Resume screening</a></li>
                <li><a href="#product" className="hover:text-ink-foreground">AI interviews</a></li>
                <li><a href="#product" className="hover:text-ink-foreground">Calling campaigns</a></li>
                <li><a href="#product" className="hover:text-ink-foreground">Analytics</a></li>
              </ul>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-ink-foreground/50">Company</p>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li><a href="https://novalantis.com" target="_blank" rel="noreferrer" className="hover:text-ink-foreground">About Novalantis</a></li>
                <li><a href="https://novalantis.com/contact-us/" target="_blank" rel="noreferrer" className="hover:text-ink-foreground">Contact sales</a></li>
              </ul>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-ink-foreground/50">Account</p>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li><Link href="/login" className="hover:text-ink-foreground">Log in</Link></li>
                <li><Link href={primaryHref} className="hover:text-ink-foreground">Get started</Link></li>
              </ul>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-ink-foreground/50">Trust</p>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li className="flex items-center gap-1.5"><Lock size={13} /> Org-scoped data access</li>
                <li className="flex items-center gap-1.5"><BarChart3 size={13} /> Auditable AI decisions</li>
              </ul>
            </div>
          </div>
          <div className="flex flex-col items-center gap-2 pt-8 text-center">
            <span className="text-sm font-bold text-ink-foreground">Hireonomous</span>
            <p className="text-[11px] font-semibold uppercase tracking-widest">
              © {new Date().getFullYear()} Hireonomous. A product by Novalantis.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
