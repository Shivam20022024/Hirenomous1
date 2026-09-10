'use client';

import { useState, useRef, useEffect } from 'react';
import { Upload, Plus, FileText, X, Check, Loader2, Briefcase, Link2, HardDrive, Building2, Share2, Globe } from 'lucide-react';
import { fetchApi, API_BASE_URL } from '@/lib/api';
import { EmptyState } from '@/components/empty-state';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';

const COMING_SOON_SOURCES = {
  linkedin: {
    label: 'LinkedIn',
    icon: Building2,
    description: 'Importing resumes directly from LinkedIn is coming soon. For now, download the resume from LinkedIn and upload it via Local.',
  },
  sharepoint: {
    label: 'SharePoint',
    icon: Share2,
    description: 'Importing resumes directly from SharePoint is coming soon. For now, download the resume from SharePoint and upload it via Local.',
  },
  naukri: {
    label: 'Naukri',
    icon: Globe,
    description: 'Importing resumes directly from Naukri is coming soon. For now, download the resume from Naukri and upload it via Local.',
  },
} as const;

export default function ResumesPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'upload' | 'manual'>('upload');

  // Upload State
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadSource, setUploadSource] = useState<'local' | 'drive' | 'linkedin' | 'sharepoint' | 'naukri'>('local');
  const [files, setFiles] = useState<File[]>([]);
  const [driveLinks, setDriveLinks] = useState<string[]>([]);
  const [driveLinkInput, setDriveLinkInput] = useState('');
  const [driveLinkError, setDriveLinkError] = useState('');
  const [jobDescription, setJobDescription] = useState('We are looking for a software engineer with Python and AI experience.');
  const [skipAi, setSkipAi] = useState(false);
  const [jobId, setJobId] = useState('');
  
  // Manual State
  const [manualData, setManualData] = useState({
    name: '',
    email: '',
    phone: '',
    skills: '',
    role: 'Manual Entry',
    job_id: ''
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchApi('/jobs').then(setJobs).catch(console.error);
  }, []);

  const handleAddDriveLink = () => {
    const link = driveLinkInput.trim();
    if (!link) return;
    if (!/^https?:\/\/(drive|docs)\.google\.com\//i.test(link)) {
      setDriveLinkError('That doesn\'t look like a Google Drive link.');
      return;
    }
    if (driveLinks.includes(link)) {
      setDriveLinkError('That link is already in the list.');
      return;
    }
    setDriveLinks(prev => [...prev, link]);
    setDriveLinkInput('');
    setDriveLinkError('');
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0 && driveLinks.length === 0) {
      setError('Please select at least one resume file, or add a Google Drive link.');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');

    let successCount = 0;
    let failCount = 0;
    const CONCURRENCY = 200; // Allow uploading up to 200 files simultaneously

    for (let i = 0; i < files.length; i += CONCURRENCY) {
      const chunk = files.slice(i, i + CONCURRENCY);

      await Promise.all(chunk.map(async (file) => {
        try {
          const formData = new FormData();
          formData.append('file', file);
          formData.append('job_description', jobDescription);
          formData.append('skip_ai', String(skipAi));
          if (jobId) formData.append('job_id', jobId);

          const token = localStorage.getItem('token');
          const res = await fetch(`${API_BASE_URL}/upload-resume`, {
            method: 'POST',
            headers: {
              ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            },
            body: formData
          });

          if (!res.ok) {
            failCount++;
            return;
          }
          successCount++;
        } catch (err: any) {
          failCount++;
        }
      }));
    }

    const DRIVE_CONCURRENCY = 15; // Matches the backend's AI HTTP client connection pool (see resume_service.py)

    const importDriveFile = async (fileRef: { drive_url?: string; file_id?: string }) => {
      try {
        await fetchApi('/upload-resume-from-drive', {
          method: 'POST',
          body: JSON.stringify({
            ...fileRef,
            job_description: jobDescription,
            skip_ai: skipAi,
            job_id: jobId || null
          })
        });
        successCount++;
      } catch (err: any) {
        failCount++;
      }
    };

    for (const link of driveLinks) {
      const isFolder = /\/folders\//i.test(link);
      if (!isFolder) {
        await importDriveFile({ drive_url: link });
        continue;
      }

      try {
        // Folders are listed first (fast), then each file is imported as its
        // own request — importing every file inside one giant request would
        // time out once a folder has more than a handful of resumes, since
        // each one needs a real AI-scoring call.
        const listRes = await fetchApi('/list-drive-folder-files', {
          method: 'POST',
          body: JSON.stringify({ drive_url: link })
        });
        const folderFiles: { file_id: string; name: string }[] = listRes.files || [];

        for (let i = 0; i < folderFiles.length; i += DRIVE_CONCURRENCY) {
          const chunk = folderFiles.slice(i, i + DRIVE_CONCURRENCY);
          await Promise.all(chunk.map(f => importDriveFile({ file_id: f.file_id })));
        }
      } catch (err: any) {
        failCount++;
      }
    }

    setLoading(false);
    if (failCount === 0) {
      setSuccess(`Successfully parsed ${successCount} resume${successCount !== 1 ? 's' : ''}.`);
    } else {
      setSuccess(`Parsed ${successCount} resume${successCount !== 1 ? 's' : ''} successfully. ${failCount} failed.`);
    }
    setFiles([]);
    setDriveLinks([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');

    try {
      await fetchApi('/add-manual', {
        method: 'POST',
        body: JSON.stringify({
          ...manualData,
          skills: manualData.skills.split(',').map(s => s.trim()).filter(Boolean),
          job_id: manualData.job_id || null
        })
      });

      setSuccess(`Successfully added ${manualData.name}`);
      setManualData({ name: '', email: '', phone: '', skills: '', role: 'Manual Entry', job_id: '' });
    } catch (err: any) {
      setError(err.message || 'An error occurred while adding candidate.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1240px] space-y-8 px-5 py-9 lg:px-8 lg:py-12">
      {/* 1. Header */}
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Candidate Profiles</h1>
          <p className="mt-2 text-base font-semibold text-foreground">Upload, parse, and organize candidate resumes in one place.</p>
        </div>
        {jobs.length > 0 && (
          <div className="flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 shadow-sm">
             <Briefcase className="h-4 w-4 text-primary" />
             <span className="text-sm font-semibold">{jobs.length} Active Jobs</span>
          </div>
        )}
      </div>

      {/* 2. Tabs */}
      <div className="flex w-full sm:w-fit rounded-lg bg-muted p-1">
        <button
          type="button"
          onClick={() => { setActiveTab('upload'); setError(''); setSuccess(''); setUploadModalOpen(true); }}
          className={`flex-1 sm:flex-none flex items-center justify-center gap-2 rounded-md px-6 py-2.5 text-sm font-bold transition-all duration-200 ${activeTab === 'upload' ? 'bg-primary text-primary-foreground shadow-md shadow-primary/30' : 'text-muted-foreground hover:text-foreground'}`}
        >
          <Upload size={16} /> Upload Resume
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('manual'); setError(''); setSuccess(''); }}
          className={`flex-1 sm:flex-none flex items-center justify-center gap-2 rounded-md px-6 py-2.5 text-sm font-bold transition-all duration-200 ${activeTab === 'manual' ? 'bg-primary text-primary-foreground shadow-md shadow-primary/30' : 'text-muted-foreground hover:text-foreground'}`}
        >
          <FileText size={16} /> Manual Entry
        </button>
      </div>

      <div className="relative">
        {error && <div className="mb-6 rounded-xl bg-destructive/10 p-4 text-sm font-medium text-destructive flex items-start gap-3"><X size={16} className="mt-0.5 shrink-0"/>{error}</div>}
        {success && <div className="mb-6 rounded-xl bg-success/10 p-4 text-sm font-medium text-success flex items-start gap-3"><Check size={16} className="mt-0.5 shrink-0"/>{success}</div>}

        {activeTab === 'upload' ? (
          <form onSubmit={handleUploadSubmit} className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
              {/* Left Column: Job & AI */}
              <div className="space-y-6 flex flex-col">
                {/* 3. Job Selection */}
                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="mb-4">
                    <h2 className="text-base font-semibold text-foreground">Match resumes to a job</h2>
                    <p className="text-sm font-semibold text-foreground mt-1">Select an active job to parse resumes against its requirements.</p>
                  </div>
                  
                  <select 
                    value={jobId} 
                    onChange={e => {
                      const newJobId = e.target.value;
                      setJobId(newJobId);
                      if (newJobId) {
                        const selectedJob = jobs.find(j => j.id === newJobId);
                        if (selectedJob && selectedJob.description) {
                          setJobDescription(selectedJob.description);
                        }
                      } else {
                        setJobDescription('');
                      }
                    }} 
                    className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm font-medium shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-colors hover:border-border/80"
                  >
                    <option value="">Select a job</option>
                    {jobs.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}
                  </select>

                  {jobId && jobs.find(j => j.id === jobId) && (
                    <div className="mt-4 flex items-center gap-2 rounded-lg bg-primary/5 px-3 py-2 border border-primary/10">
                      <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
                        <Briefcase className="h-3.5 w-3.5 text-primary" />
                      </div>
                      <span className="text-xs font-semibold text-primary">
                        {jobs.find(j => j.id === jobId)?.title} 
                        {jobs.find(j => j.id === jobId)?.experience ? ` · ${jobs.find(j => j.id === jobId)?.experience}` : ''}
                      </span>
                    </div>
                  )}
                </div>

                {/* 4. AI Matching */}
                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm flex-1 flex flex-col">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h2 className="text-base font-semibold text-foreground">AI Matching</h2>
                      <p className="text-sm font-semibold text-foreground mt-1">Use the selected job description to evaluate resume relevance.</p>
                    </div>
                  </div>

                  <div className="flex-1">
                    <textarea 
                      value={jobDescription} 
                      onChange={e => setJobDescription(e.target.value)} 
                      disabled={skipAi}
                      placeholder="Paste job description here..."
                      className="w-full h-full min-h-[120px] rounded-xl border border-border bg-background p-4 text-sm shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none disabled:opacity-50 disabled:bg-muted transition-colors resize-none" 
                    />
                  </div>

                  <div className="mt-5 flex items-start gap-3 rounded-xl border border-border bg-muted/30 p-4">
                    <div className="relative flex h-5 items-center justify-center">
                      <input 
                        type="checkbox" 
                        id="skipAi" 
                        checked={skipAi} 
                        onChange={e => setSkipAi(e.target.checked)}
                        className="peer h-4 w-4 cursor-pointer appearance-none rounded-sm border border-border bg-background checked:border-primary checked:bg-primary focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 transition-all"
                      />
                      <Check className="pointer-events-none absolute h-3 w-3 stroke-[3] text-white opacity-0 peer-checked:opacity-100 transition-opacity" />
                    </div>
                    <div className="flex flex-col">
                      <label htmlFor="skipAi" className="text-sm font-semibold text-foreground cursor-pointer select-none">Skip AI Analysis</label>
                      <span className="text-sm font-semibold text-foreground mt-0.5">Resume will be parsed without scoring or AI matching.</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column: Upload Area */}
              <div className="flex flex-col gap-6">
                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm flex-1 flex flex-col">
                  <div className="mb-4">
                    <h2 className="text-base font-semibold text-foreground">Upload Resumes</h2>
                    <p className="text-sm font-semibold text-foreground mt-1">Add candidate resumes from your computer, or import from a connected source.</p>
                  </div>

                  {/* 5. Trigger — opens the upload dialog */}
                  <button
                    type="button"
                    onClick={() => setUploadModalOpen(true)}
                    className="group flex flex-1 min-h-[180px] flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-primary/40 bg-primary/5 px-6 py-10 text-center transition-all hover:bg-primary/10"
                  >
                    <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 transition-transform group-hover:scale-110">
                      <Upload className="h-6 w-6 text-primary" />
                    </div>
                    <h3 className="text-sm font-bold text-foreground">Upload Resume</h3>
                    <p className="mt-1 max-w-xs text-sm font-semibold text-foreground">Choose a file from your computer, or import from LinkedIn, SharePoint, Naukri, or Google Drive</p>
                  </button>

                  {/* Selected files / links */}
                  {(files.length > 0 || driveLinks.length > 0) && (
                    <div className="mt-6 flex flex-col gap-2 max-h-[200px] overflow-y-auto pr-1">
                      <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                        <span>{files.length + driveLinks.length} item{files.length + driveLinks.length !== 1 ? 's' : ''} selected</span>
                        <button type="button" onClick={() => { setFiles([]); setDriveLinks([]); }} className="text-destructive hover:underline normal-case tracking-normal">Clear all</button>
                      </div>
                      {files.map((file, idx) => (
                        <div key={`file-${idx}`} className="flex items-center justify-between rounded-xl border border-border bg-background p-2.5 shadow-[0_2px_8px_rgba(0,0,0,0.02)] transition-colors hover:border-border/80">
                          <div className="flex items-center gap-3 overflow-hidden">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                              <FileText size={16} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-semibold text-foreground">{file.name}</p>
                              <p className="text-xs font-medium text-muted-foreground">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setFiles(files.filter((_, i) => i !== idx));
                            }}
                            className="ml-4 shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                          >
                            <X size={16} />
                          </button>
                        </div>
                      ))}
                      {driveLinks.map((link, idx) => (
                        <div key={`link-${idx}`} className="flex items-center justify-between rounded-xl border border-border bg-background p-2.5 shadow-[0_2px_8px_rgba(0,0,0,0.02)] transition-colors hover:border-border/80">
                          <div className="flex items-center gap-3 overflow-hidden">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                              <Link2 size={16} />
                            </div>
                            <p className="truncate text-sm font-semibold text-foreground">{link}</p>
                          </div>
                          <button
                            type="button"
                            onClick={() => setDriveLinks(prev => prev.filter((_, i) => i !== idx))}
                            className="ml-4 shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                          >
                            <X size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Upload source dialog */}
            <Dialog open={uploadModalOpen} onOpenChange={setUploadModalOpen}>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>Upload new resume</DialogTitle>
                  <DialogDescription>
                    {uploadSource === 'local' && 'Select resume files from your computer.'}
                    {uploadSource === 'drive' && 'Import resumes from a Google Drive link.'}
                    {uploadSource in COMING_SOON_SOURCES && `Import resumes from ${COMING_SOON_SOURCES[uploadSource as keyof typeof COMING_SOON_SOURCES].label}.`}
                  </DialogDescription>
                </DialogHeader>

                <div className="mb-5 flex flex-wrap gap-1 rounded-lg bg-muted p-1">
                  <button
                    type="button"
                    onClick={() => setUploadSource('local')}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-black transition-colors ${uploadSource === 'local' ? 'bg-card text-foreground shadow-sm' : 'text-foreground/70 hover:text-foreground'}`}
                  >
                    <HardDrive size={13} /> Local
                  </button>
                  <button
                    type="button"
                    onClick={() => setUploadSource('drive')}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-black transition-colors ${uploadSource === 'drive' ? 'bg-card text-foreground shadow-sm' : 'text-foreground/70 hover:text-foreground'}`}
                  >
                    <Link2 size={13} /> Google Drive
                  </button>
                  {(Object.entries(COMING_SOON_SOURCES) as [keyof typeof COMING_SOON_SOURCES, typeof COMING_SOON_SOURCES[keyof typeof COMING_SOON_SOURCES]][]).map(([key, src]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setUploadSource(key)}
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-black transition-colors ${uploadSource === key ? 'bg-card text-foreground shadow-sm' : 'text-foreground/70 hover:text-foreground'}`}
                    >
                      <src.icon size={13} /> {src.label}
                    </button>
                  ))}
                </div>

                {uploadSource === 'local' ? (
                  <label className="group relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-primary/40 bg-primary/5 px-6 py-10 text-center transition-all hover:bg-primary/10">
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      className="sr-only"
                      onChange={e => {
                        const newFiles = Array.from(e.target.files || []);
                        if (newFiles.length > 0) {
                          setFiles(prev => [...prev, ...newFiles]);
                          setUploadModalOpen(false);
                        }
                      }}
                      accept=".pdf,.docx,.doc"
                    />
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 transition-transform group-hover:scale-110">
                      <Upload className="h-6 w-6 text-primary" />
                    </div>
                    <h3 className="text-sm font-bold text-foreground">Drop file here</h3>
                    <p className="mt-1 text-xs text-muted-foreground">or</p>
                    <div className="mt-3 flex items-center justify-center rounded-lg bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground shadow-sm transition-colors group-hover:opacity-90">
                      Select file to upload
                    </div>
                    <p className="mt-5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">PDF, DOCX • Up to 10 MB per file</p>
                  </label>
                ) : uploadSource === 'drive' ? (
                  <div className="flex flex-col items-center rounded-xl border-2 border-dashed border-primary/40 bg-primary/5 px-6 py-10 text-center">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                      <Link2 className="h-6 w-6 text-primary" />
                    </div>
                    <h3 className="text-sm font-bold text-foreground">Import from Google Drive</h3>
                    <p className="mt-1 text-sm font-semibold text-foreground">Paste a shareable link to a resume file, or an entire folder. Sharing must be set to "Anyone with the link can view".</p>

                    <div className="mt-6 flex w-full items-center gap-2">
                      <input
                        type="url"
                        value={driveLinkInput}
                        onChange={e => { setDriveLinkInput(e.target.value); setDriveLinkError(''); }}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleAddDriveLink(); } }}
                        placeholder="https://drive.google.com/file/d/..."
                        className="h-11 flex-1 rounded-xl border border-border bg-background px-3.5 text-sm shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={handleAddDriveLink}
                        className="flex h-11 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-sm hover:opacity-90"
                      >
                        Add
                      </button>
                    </div>
                    {driveLinkError && <p className="mt-2 text-xs font-medium text-destructive">{driveLinkError}</p>}
                    <p className="mt-5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">PDF, DOCX • File or folder link</p>
                  </div>
                ) : (
                  <EmptyState
                    icon={(() => { const Icon = COMING_SOON_SOURCES[uploadSource].icon; return <Icon size={22} />; })()}
                    title={`${COMING_SOON_SOURCES[uploadSource].label} import is coming soon`}
                    description={COMING_SOON_SOURCES[uploadSource].description}
                    action={
                      <button
                        type="button"
                        onClick={() => setUploadSource('local')}
                        className="mt-1 rounded-lg border border-border bg-card px-4 py-2 text-xs font-semibold shadow-sm hover:bg-muted transition-colors"
                      >
                        Upload from Local instead
                      </button>
                    }
                  />
                )}
              </DialogContent>
            </Dialog>

            {/* 6. Submit Button */}
            <button
              type="submit"
              disabled={loading || (files.length === 0 && driveLinks.length === 0)}
              className="w-full flex h-14 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-accent px-8 text-lg font-bold text-primary-foreground shadow-lg shadow-primary/25 transition-all hover:scale-[1.01] active:scale-[0.99] disabled:pointer-events-none disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 tracking-wide"
            >
              {loading ? (
                <><Loader2 className="h-5 w-5 animate-spin" /> Processing Resumes...</>
              ) : (
                <><Upload className="h-5 w-5" /> Upload & Parse Resumes</>
              )}
            </button>
          </form>
        ) : (
          <div className="rounded-2xl border border-border bg-card p-8 shadow-sm max-w-2xl">
            {/* 7. Manual Entry (Cleaned up) */}
            <div className="mb-8 border-b border-border pb-5">
              <h2 className="text-lg font-bold text-foreground">Manual Candidate Entry</h2>
              <p className="text-base font-semibold text-foreground mt-1">Add a candidate's details directly into the database.</p>
            </div>
            <form onSubmit={handleManualSubmit} className="space-y-6">
              <div className="grid gap-6 sm:grid-cols-2">
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Full Name</label>
                  <input required value={manualData.name} onChange={e => setManualData({...manualData, name: e.target.value})} className="mt-2 w-full rounded-xl border border-border bg-background px-4 py-3.5 text-sm font-medium shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-colors hover:border-border/80" placeholder="John Doe" />
                </div>
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Email Address</label>
                  <input required type="email" value={manualData.email} onChange={e => setManualData({...manualData, email: e.target.value})} className="mt-2 w-full rounded-xl border border-border bg-background px-4 py-3.5 text-sm font-medium shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-colors hover:border-border/80" placeholder="john@example.com" />
                </div>
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Phone Number</label>
                  <input required value={manualData.phone} onChange={e => setManualData({...manualData, phone: e.target.value})} className="mt-2 w-full rounded-xl border border-border bg-background px-4 py-3.5 text-sm font-medium shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-colors hover:border-border/80" placeholder="+1 (555) 000-0000" />
                </div>
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Assign to Job</label>
                  <select value={manualData.job_id} onChange={e => setManualData({...manualData, job_id: e.target.value})} className="mt-2 w-full rounded-xl border border-border bg-background px-4 py-3.5 text-sm font-medium shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-colors hover:border-border/80">
                    <option value="">No specific job</option>
                    {jobs.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Key Skills</label>
                  <input value={manualData.skills} onChange={e => setManualData({...manualData, skills: e.target.value})} className="mt-2 w-full rounded-xl border border-border bg-background px-4 py-3.5 text-sm font-medium shadow-sm focus:border-primary focus:ring-1 focus:ring-primary focus:outline-none transition-colors hover:border-border/80" placeholder="e.g. Python, React, FastApi" />
                </div>
              </div>
              <button 
                type="submit" 
                disabled={loading}
                className="w-full flex h-14 items-center justify-center gap-2 rounded-xl bg-primary px-8 text-base font-bold text-primary-foreground shadow-lg shadow-primary/25 transition-all hover:opacity-90 disabled:opacity-50 disabled:shadow-none focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 mt-4"
              >
                {loading ? <><Loader2 className="h-5 w-5 animate-spin" /> Saving Candidate...</> : <><Plus className="h-5 w-5" /> Add Candidate Profile</>}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
