'use client';

import { useState, useEffect, useRef } from 'react';
import { Phone, Users, CheckCircle, Clock, PlayCircle, Loader2, RefreshCw, Trash2, ChevronDown } from 'lucide-react';
import { fetchApi } from '@/lib/api';
import { PageHeader } from '@/components/page-header';
import { StatTile } from '@/components/stat-tile';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';

export default function CampaignsPage() {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [selectedJobs, setSelectedJobs] = useState<string[]>([]);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'pending' | 'completed'>('pending');
  const [selectedForDeletion, setSelectedForDeletion] = useState<string[]>([]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [candidatesData, jobsData] = await Promise.all([
        fetchApi('/candidates'),
        fetchApi('/jobs')
      ]);
      setCandidates(candidatesData);
      setJobs(jobsData);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCallAll = async () => {
    if (selectedJobs.length === 0) {
      alert('Select at least one job posting before starting calls.');
      return;
    }
    if (!confirm('Are you sure you want to initiate AI calls to shortlisted candidates for the selected job(s)?')) return;

    setActionLoading(true);
    try {
      const res = await fetchApi('/bolna/call-shortlisted', {
        method: 'POST',
        body: JSON.stringify(selectedJobs.length > 0 ? { job_ids: selectedJobs } : {})
      });

      let reportMessage = `Total calls queued: ${res.called_count}\n`;
      if (res.results && res.results.length > 0) {
        reportMessage += `\nResults by Job:\n`;
        res.results.forEach((r: any) => {
          reportMessage += `- ${r.job_title}: Queued ${r.calls_queued}/${r.shortlisted_found}`;
          if (r.failed > 0) reportMessage += ` (Failed: ${r.failed})`;
          reportMessage += '\n';
        });
      }
      alert(reportMessage);
      loadData();
    } catch (err: any) {
      alert(`Failed to call: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCallSingle = async (candidateId: string) => {
    setActionLoading(true);
    try {
      await fetchApi(`/bolna/call-candidate/${candidateId}`, { method: 'POST' });
      alert('Call initiated successfully.');
      loadData();
    } catch (err: any) {
      alert(`Failed to call: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSyncSingle = async (candidateId: string) => {
    setActionLoading(true);
    try {
      await fetchApi(`/bolna/sync-call/${candidateId}`);
      // No need to alert on every single one, just reload data to see if it changed
      loadData();
    } catch (err: any) {
      alert(`Failed to sync call: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const filteredCandidates = selectedJobs.length === 0 ? candidates : candidates.filter(c => selectedJobs.includes(c.job_id));
  const pendingCalls = filteredCandidates.filter(c => !['calling', 'completed', 'interested', 'not_interested', 'callback_required', 'selected', 'hired'].includes(c.status?.toLowerCase()));
  const completedCalls = filteredCandidates.filter(c => ['completed', 'interested', 'not_interested', 'callback_required', 'selected', 'hired'].includes(c.status?.toLowerCase()) || c.call_status === 'completed');
  const activeCalls = filteredCandidates.filter(c => c.status === 'calling');

  const handleSyncAllActive = async () => {
    if (activeCalls.length === 0) return;
    setActionLoading(true);
    try {
      await Promise.all(activeCalls.map(c => fetchApi(`/bolna/sync-call/${c.candidate_id}`)));
      loadData();
    } catch (err: any) {
      alert(`Failed to sync calls: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteAllCompleted = async () => {
    if (selectedForDeletion.length === 0) return;
    if (!confirm(`Are you sure you want to delete ${selectedForDeletion.length} selected candidates?`)) return;
    setActionLoading(true);
    try {
      await fetchApi(`/candidates/bulk`, {
        method: 'DELETE',
        body: JSON.stringify({ candidate_ids: selectedForDeletion })
      });
      setSelectedForDeletion([]);
      loadData();
    } catch (err: any) {
      alert(`Failed to delete candidates: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const displayCandidates = activeTab === 'pending' ? [...activeCalls, ...pendingCalls] : completedCalls;

  return (
    <div className="mx-auto max-w-[1240px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <div className="flex flex-col gap-5">
        <PageHeader
          eyebrow="Outreach"
          title="Calling Campaigns"
          description="Manage and track automated AI screening calls."
        />
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="flex items-center justify-between h-11 rounded-lg border border-border bg-card px-4 text-sm font-semibold text-foreground min-w-[200px]"
            >
              <span>{selectedJobs.length === 0 ? 'All Postings' : `${selectedJobs.length} Job${selectedJobs.length > 1 ? 's' : ''} Selected`}</span>
              <ChevronDown size={16} className="ml-2 text-muted-foreground" />
            </button>

            {isDropdownOpen && (
              <div className="absolute top-12 left-0 z-50 w-64 rounded-lg border border-border bg-card p-2 shadow-xl max-h-[300px] overflow-y-auto">
                <div className="flex gap-2 mb-2 pb-2 border-b border-border px-2">
                  <button onClick={() => setSelectedJobs(jobs.map(j => j.id))} className="text-xs font-semibold text-primary hover:underline">Select All</button>
                  <button onClick={() => setSelectedJobs([])} className="text-xs font-semibold text-muted-foreground hover:underline">Clear All</button>
                </div>
                {jobs.map(job => (
                  <label key={job.id} className="flex items-center gap-2 p-2 hover:bg-muted rounded-md cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedJobs.includes(job.id)}
                      onChange={() => {
                        setSelectedJobs(prev => prev.includes(job.id) ? prev.filter(id => id !== job.id) : [...prev, job.id]);
                      }}
                      className="rounded border-border accent-primary"
                    />
                    <span className="text-sm font-medium line-clamp-1 text-foreground">{job.title}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <Button
            variant="outline"
            size="lg"
            onClick={handleSyncAllActive}
            disabled={actionLoading || activeCalls.length === 0}
          >
            {actionLoading ? <Loader2 size={16} className="animate-spin"/> : <RefreshCw size={16} />}
            Sync Active ({activeCalls.length})
          </Button>
          <Button
            variant="destructive"
            size="lg"
            onClick={handleDeleteAllCompleted}
            disabled={actionLoading || selectedForDeletion.length === 0}
          >
            {actionLoading ? <Loader2 size={16} className="animate-spin"/> : <Trash2 size={16} />}
            Delete Selected ({selectedForDeletion.length})
          </Button>
          <Button
            size="lg"
            onClick={handleCallAll}
            disabled={actionLoading || selectedJobs.length === 0 || pendingCalls.filter(c => c.status === 'shortlisted' || (c.score && c.score >= 70)).length === 0}
            title={selectedJobs.length === 0 ? 'Select at least one job posting first' : undefined}
          >
            {actionLoading ? <Loader2 size={16} className="animate-spin"/> : <PlayCircle size={16} />}
            Call All Shortlisted ({pendingCalls.filter(c => c.status === 'shortlisted' || (c.score && c.score >= 70)).length})
          </Button>
        </div>
        {selectedJobs.length === 0 && (
          <p className="text-sm font-semibold text-foreground">
            Select one or more job postings above to enable “Call All Shortlisted”.
          </p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="Uncalled Candidates" value={pendingCalls.length} icon={<Users size={16}/>} tone="neutral" />
        <StatTile label="Active Calls" value={activeCalls.length} icon={<Phone size={16}/>} tone="warning" />
        <StatTile label="Completed Calls" value={completedCalls.length} icon={<CheckCircle size={16}/>} tone="success" />
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="border-b border-border bg-muted/20 p-3">
          <Tabs>
            <TabsList>
              <TabsTrigger active={activeTab === 'pending'} onClick={() => setActiveTab('pending')}>
                Uncalled &amp; Active ({pendingCalls.length + activeCalls.length})
              </TabsTrigger>
              <TabsTrigger active={activeTab === 'completed'} onClick={() => setActiveTab('completed')}>
                Completed ({completedCalls.length})
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {loading ? (
          <div className="p-12 text-center"><div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div></div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">
                  <input
                    type="checkbox"
                    className="rounded border-border accent-primary w-4 h-4"
                    checked={displayCandidates.length > 0 && selectedForDeletion.length === displayCandidates.length}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedForDeletion(displayCandidates.map(c => c.candidate_id));
                      } else {
                        setSelectedForDeletion([]);
                      }
                    }}
                  />
                </TableHead>
                <TableHead>Candidate</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayCandidates.length > 0 ? displayCandidates.map(candidate => (
                <TableRow key={candidate.candidate_id} className={selectedForDeletion.includes(candidate.candidate_id) ? 'bg-muted/40' : ''}>
                  <TableCell>
                    <input
                      type="checkbox"
                      className="rounded border-border accent-primary w-4 h-4"
                      checked={selectedForDeletion.includes(candidate.candidate_id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedForDeletion(prev => [...prev, candidate.candidate_id]);
                        } else {
                          setSelectedForDeletion(prev => prev.filter(id => id !== candidate.candidate_id));
                        }
                      }}
                    />
                  </TableCell>
                  <TableCell className="font-medium">{candidate.name}</TableCell>
                  <TableCell className="text-muted-foreground">{candidate.role || 'N/A'}</TableCell>
                  <TableCell className="text-muted-foreground">{candidate.phone}</TableCell>
                  <TableCell>
                    {candidate.status === 'calling' ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/20 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-warning-text">
                        <span className="h-1.5 w-1.5 rounded-full bg-warning-text animate-pulse"></span> Calling
                      </span>
                    ) : candidate.call_status === 'completed' ? (
                      <span className="inline-flex items-center rounded-full bg-success/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-success">Completed</span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-muted px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Pending</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {activeTab === 'pending' && candidate.status === 'calling' && (
                      <button onClick={() => handleSyncSingle(candidate.candidate_id)} disabled={actionLoading} className="text-primary flex items-center gap-1 hover:underline font-semibold disabled:opacity-50">
                        <RefreshCw size={12} /> Sync Status
                      </button>
                    )}
                    {activeTab === 'pending' && candidate.status !== 'calling' && (
                      <button onClick={() => handleCallSingle(candidate.candidate_id)} disabled={actionLoading} className="text-primary hover:underline font-semibold disabled:opacity-50">
                        Call Now
                      </button>
                    )}
                    {activeTab === 'completed' && (
                      <div className="flex flex-col text-xs gap-1">
                        {candidate.interest && <span><span className="font-semibold text-muted-foreground">Interest:</span> {candidate.interest}</span>}
                        {candidate.communication_score && <span><span className="font-semibold text-muted-foreground">Comm:</span> {candidate.communication_score}/100</span>}
                        {candidate.recording_url && <a href={candidate.recording_url} target="_blank" rel="noreferrer" className="text-primary hover:underline mt-1">Listen Recording</a>}
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              )) : (
                <TableRow>
                  <TableCell colSpan={6} className="py-12 text-center text-muted-foreground">
                    No candidates found in this category.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
