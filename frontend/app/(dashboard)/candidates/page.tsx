'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Mail, Phone, Download, Clock, Trash2, X, FileText, Play, Eye, Loader2, ClipboardCheck, Check } from 'lucide-react';
import { fetchApi } from '@/lib/api';
import { PageHeader } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';

export default function CandidatesPage() {
  const router = useRouter();
  const [candidates, setCandidates] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [jobId, setJobId] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState<any>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [candidatesData, jobsData] = await Promise.all([
        fetchApi(jobId ? `/candidates?job_id=${jobId}` : '/candidates'),
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
  }, [jobId]);

  const handleExport = async () => {
    try {
      const blob = await fetchApi(`/export/candidates${jobId ? `?job_id=${jobId}` : ''}`);
      if (blob) {
        const url = window.URL.createObjectURL(blob as Blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `candidates_export.xlsx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Failed to export', err);
    }
  };

  const interestedCount = candidates.filter(c => c.status?.toLowerCase() === 'interested').length;
  const jobName = jobId ? (jobs.find(j => j.id === jobId)?.title || 'the selected job') : null;

  const handleSendEmail = async () => {
    if (!jobId) { alert('Select a specific job before sending emails.'); return; }
    if (!confirm(
      `Send the "shortlisted" notification email to the ${interestedCount} interested candidate(s) for "${jobName}"?\n\n` +
      `This email has no interview link.`
    )) return;
    setActionLoading(true);
    try {
      const res = await fetchApi(`/email/send-shortlisted${jobId ? `?job_id=${jobId}` : ''}`, { method: 'POST' });
      alert(res.message || 'Emails sent successfully.');
      loadData();
    } catch (err: any) {
      alert(`Failed to send emails: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleBulkInvite = async () => {
    if (!jobId) { alert('Select a specific job before inviting candidates to an AI Interview.'); return; }
    if (!confirm(
      `Invite the ${interestedCount} interested candidate(s) for "${jobName}" to an AI video interview?\n\n` +
      `This creates an interview and emails a secure interview link to each. It does NOT select anyone.`
    )) return;
    setActionLoading(true);
    try {
      const res = await fetchApi('/interviews/bulk-invite', {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId || null }),
      });
      alert(res.message || 'Interview invitations processed.');
      loadData();
    } catch (err: any) {
      alert(`Bulk invite failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCallSingle = async (e: React.MouseEvent, candidateId: string) => {
    e.stopPropagation();
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

  const handleInviteInterview = async (candidate: any) => {
    if (!confirm(`Invite ${candidate.name} to an AI interview? This does NOT select the candidate.`)) return;
    setActionLoading(true);
    try {
      const res = await fetchApi('/interviews', {
        method: 'POST',
        body: JSON.stringify({ candidate_id: candidate.candidate_id, job_id: candidate.job_id || null }),
      });
      const iid = res?.interview?.id;
      if (res?.created === false) {
        alert('This candidate already has an active AI interview — no new invite was sent.');
      } else if (res?.invite?.sent) {
        alert('AI interview created and invitation email sent.');
      } else {
        alert(`AI interview created. Invitation email not sent (${res?.invite?.reason || 'no email / SMTP not configured'}). Link: ${res?.interview_url || 'n/a'}`);
      }
      await loadData();
      if (iid) router.push(`/interviews/${iid}`);
    } catch (err: any) {
      alert(`Failed to create interview: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleInterviewDecision = async (candidate: any, decision: 'select' | 'reject') => {
    if (!candidate.latest_interview_id) {
      alert('No interview found for this candidate.');
      return;
    }
    if (!confirm(`Are you sure you want to ${decision} ${candidate.name}?`)) return;
    setActionLoading(true);
    try {
      const res = await fetchApi(`/interviews/${candidate.latest_interview_id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      });
      if (decision === 'select') {
        const em = res?.selection_email;
        alert(em?.sent ? 'Candidate selected — selection email sent.' : `Candidate selected. Selection email not sent (${em?.errors?.[0] || 'SMTP not configured'}).`);
      }
      setSelectedCandidate(null);
      await loadData();
    } catch (err: any) {
      alert(`Failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, candidateId: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this candidate?')) return;
    try {
      await fetchApi(`/candidates/${candidateId}`, { method: 'DELETE' });
      setCandidates(prev => prev.filter(c => c.candidate_id !== candidateId));
      if (selectedCandidate?.candidate_id === candidateId) {
        setSelectedCandidate(null);
      }
    } catch (err) {
      console.error('Failed to delete candidate', err);
      alert('Failed to delete candidate');
    }
  };


  const filteredCandidates = candidates.filter(c => {
    const q = query.toLowerCase();
    const matchesSearch = c.name?.toLowerCase().includes(q) ||
                          c.email?.toLowerCase().includes(q) ||
                          c.role?.toLowerCase().includes(q);
    const matchesStatus = statusFilter ? c.status?.toUpperCase() === statusFilter : true;
    return matchesSearch && matchesStatus;
  });

  if (loading) return <div className="p-12 text-center"><div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div></div>;

  return (
    <div className="mx-auto max-w-[1240px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <PageHeader
        eyebrow="Pipeline"
        title="Candidates"
        description="View and manage all candidates across your organization."
      />

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground">
          <Search size={16}/>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search candidates" className="bg-transparent outline-none placeholder:text-muted-foreground"/>
        </label>
        <Select value={jobId} onChange={e => setJobId(e.target.value)} className="h-11 w-auto min-w-[160px]">
          <option value="">All Jobs</option>
          {jobs.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}
        </Select>
        <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="h-11 w-auto min-w-[160px]">
          <option value="">All Statuses</option>
          <option value="SHORTLISTED">Shortlisted</option>
          <option value="CALLING">Calling</option>
          <option value="INTERESTED">Interested</option>
          <option value="CALLBACK_REQUIRED">Callback Required</option>
          <option value="NOT_INTERESTED">Not Interested</option>
          <option value="INTERVIEW">AI Interview</option>
          <option value="INTERVIEW_COMPLETED">Interview Completed</option>
          <option value="SELECTED">Selected</option>
          <option value="REJECTED">Rejected</option>
          <option value="HIRED">Hired</option>
        </Select>
        <Button
          size="lg"
          onClick={handleBulkInvite}
          disabled={actionLoading || !jobId}
          title={!jobId ? 'Select a specific job first' : undefined}
        >
          {actionLoading ? <Loader2 size={16} className="animate-spin"/> : <ClipboardCheck size={16} />} Invite to AI Interview
        </Button>
        <Button
          variant="outline"
          size="lg"
          onClick={handleSendEmail}
          disabled={actionLoading || !jobId}
          title={!jobId ? 'Select a specific job first' : undefined}
        >
          {actionLoading ? <Loader2 size={16} className="animate-spin"/> : <Mail size={16} />} Email Interested
        </Button>
        <Button variant="secondary" size="lg" onClick={handleExport}>
          <Download size={16} /> Export
        </Button>
      </div>

      {!jobId && (
        <p className="text-xs text-muted-foreground">
          Select a specific job in the <span className="font-semibold">All Jobs</span> filter to enable “Invite to AI Interview” and “Email Interested” for that job’s candidates.
        </p>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Candidate</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Score</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Contact</TableHead>
            <TableHead>Date</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filteredCandidates.length > 0 ? filteredCandidates.map(candidate => (
            <TableRow
              key={candidate.candidate_id}
              className="cursor-pointer"
              onClick={() => setSelectedCandidate(candidate)}
            >
              <TableCell>
                <div className="font-medium text-foreground">{candidate.name || 'Unknown'}</div>
                <div className="text-xs text-muted-foreground max-w-[200px] truncate">{candidate.summary || 'No summary'}</div>
              </TableCell>
              <TableCell className="text-muted-foreground">{candidate.role || 'Unassigned'}</TableCell>
              <TableCell>
                <span className="font-mono font-semibold">{candidate.score || 0}%</span>
              </TableCell>
              <TableCell>
                <StatusPill domain="candidate" status={candidate.status?.toLowerCase() || 'uploaded'} label={candidate.status || 'uploaded'} />
              </TableCell>
              <TableCell>
                <div className="flex flex-col gap-1 text-xs text-muted-foreground">
                  {candidate.email && <span className="flex items-center gap-1"><Mail size={12}/>{candidate.email}</span>}
                  {candidate.phone && <span className="flex items-center gap-1"><Phone size={12}/>{candidate.phone}</span>}
                </div>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {candidate.created_at ? new Date(candidate.created_at).toLocaleDateString() : 'N/A'}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-2">
                  {candidate.status?.toUpperCase() === 'CALLBACK_REQUIRED' && (
                    <button
                      onClick={(e) => handleCallSingle(e, candidate.candidate_id)}
                      disabled={actionLoading}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
                      title="Call Now"
                    >
                      <Phone size={16} />
                    </button>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); setSelectedCandidate(candidate); }}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
                    title="View Details"
                  >
                    <Eye size={16} />
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, candidate.candidate_id)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                    title="Delete Candidate"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </TableCell>
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={7} className="py-12 text-center text-muted-foreground">
                No candidates found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={!!selectedCandidate} onOpenChange={(open) => !open && setSelectedCandidate(null)}>
        <DialogContent className="max-w-3xl">
          {selectedCandidate && (
            <>
              <DialogHeader>
                <DialogTitle>Candidate Details</DialogTitle>
              </DialogHeader>

              <div className="space-y-6">
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                  <div>
                    <h3 className="text-2xl font-bold text-foreground">{selectedCandidate.name || 'Unknown'}</h3>
                    <p className="text-muted-foreground">{selectedCandidate.role || 'Unassigned Role'}</p>
                  </div>
                  <div className="flex gap-2">
                    <StatusPill domain="candidate" status={selectedCandidate.status?.toLowerCase() || 'uploaded'} label={selectedCandidate.status || 'uploaded'} />
                    <span className="inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                      Score: {selectedCandidate.score || 0}%
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 rounded-xl bg-muted/50 p-4 text-sm">
                  {selectedCandidate.email && (
                    <div className="flex items-center gap-2"><Mail size={14} className="text-muted-foreground"/> {selectedCandidate.email}</div>
                  )}
                  {selectedCandidate.phone && (
                    <div className="flex items-center gap-2"><Phone size={14} className="text-muted-foreground"/> {selectedCandidate.phone}</div>
                  )}
                  {selectedCandidate.created_at && (
                    <div className="flex items-center gap-2"><Clock size={14} className="text-muted-foreground"/> {new Date(selectedCandidate.created_at).toLocaleString()}</div>
                  )}
                </div>

                {/* AI Interview actions — mirror the hiring flow: invite (interested) -> view (in progress) -> report + decide (completed) */}
                {(['interested', 'interview', 'interview_completed'].includes(String(selectedCandidate.status).toLowerCase()) || selectedCandidate.latest_interview_id) && (
                  <div className="flex flex-wrap items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 p-4">
                    <ClipboardCheck size={16} className="text-primary" />
                    <span className="text-sm font-semibold text-foreground mr-1">AI Interview</span>

                    {String(selectedCandidate.status).toLowerCase() === 'interested' && !selectedCandidate.latest_interview_id && (
                      <Button size="sm" onClick={() => handleInviteInterview(selectedCandidate)} disabled={actionLoading}>
                        {actionLoading ? <Loader2 size={13} className="animate-spin" /> : <ClipboardCheck size={13} />} Invite to AI Interview
                      </Button>
                    )}

                    {selectedCandidate.latest_interview_id && String(selectedCandidate.status).toLowerCase() === 'interview' && (
                      <Button size="sm" variant="outline" onClick={() => router.push(`/interviews/${selectedCandidate.latest_interview_id}`)}>
                        <Eye size={13} /> View Interview
                      </Button>
                    )}

                    {selectedCandidate.latest_interview_id && String(selectedCandidate.status).toLowerCase() === 'interview_completed' && (
                      <>
                        <Button size="sm" variant="outline" onClick={() => router.push(`/interviews/${selectedCandidate.latest_interview_id}`)}>
                          <FileText size={13} /> View AI Report
                        </Button>
                        <Button size="sm" variant="success" onClick={() => handleInterviewDecision(selectedCandidate, 'select')} disabled={actionLoading}>
                          <Check size={13} /> Select Candidate
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => handleInterviewDecision(selectedCandidate, 'reject')} disabled={actionLoading}>
                          <X size={13} /> Reject Candidate
                        </Button>
                      </>
                    )}

                    {['selected', 'rejected'].includes(String(selectedCandidate.status).toLowerCase()) && selectedCandidate.latest_interview_id && (
                      <Button size="sm" variant="outline" onClick={() => router.push(`/interviews/${selectedCandidate.latest_interview_id}`)}>
                        <FileText size={13} /> View AI Report
                      </Button>
                    )}
                  </div>
                )}

                {selectedCandidate.summary && (
                  <div>
                    <h4 className="mb-2 font-semibold text-foreground flex items-center gap-2"><FileText size={16}/> Summary</h4>
                    <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground leading-relaxed">
                      {selectedCandidate.summary}
                    </div>
                  </div>
                )}

                {selectedCandidate.transcript && (
                  <div>
                    <h4 className="mb-2 font-semibold text-foreground">AI Conversation Transcript</h4>
                    <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground whitespace-pre-wrap font-mono h-64 overflow-y-auto">
                      {selectedCandidate.transcript}
                    </div>
                  </div>
                )}

                {selectedCandidate.recording_url && (
                  <div>
                    <h4 className="mb-2 font-semibold text-foreground flex items-center gap-2"><Play size={16}/> Recording</h4>
                    <audio controls src={selectedCandidate.recording_url} className="w-full mt-2" />
                  </div>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
