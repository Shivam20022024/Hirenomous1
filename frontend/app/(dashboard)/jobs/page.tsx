'use client';

import { useState, useEffect } from 'react';
import { Plus, Search, Edit2, Trash2, MapPin, Clock, Briefcase } from 'lucide-react';
import { fetchApi } from '@/lib/api';
import { PageHeader } from '@/components/page-header';
import { EmptyState } from '@/components/empty-state';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

export default function JobsPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [formData, setFormData] = useState({
    id: '',
    title: '',
    description: '',
    skills: '',
    experience: '',
    location: '',
    jobType: ''
  });

  const loadJobs = async () => {
    try {
      const data = await fetchApi('/jobs');
      setJobs(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        title: formData.title,
        description: formData.description,
        skills: formData.skills.split(',').map(s => s.trim()).filter(Boolean),
        experience: formData.experience,
        location: formData.location,
        jobType: formData.jobType
      };

      if (formData.id) {
        await fetchApi(`/job/${formData.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload)
        });
      } else {
        await fetchApi('/job', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
      }
      setIsModalOpen(false);
      loadJobs();
    } catch (err) {
      console.error(err);
      alert('Failed to save job');
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this job?')) {
      try {
        await fetchApi(`/job/${id}`, { method: 'DELETE' });
        loadJobs();
      } catch (err) {
        console.error(err);
        alert('Failed to delete job');
      }
    }
  };

  const openModal = (job?: any) => {
    if (job) {
      setFormData({
        id: job.id,
        title: job.title,
        description: job.description,
        skills: job.skills?.join(', ') || '',
        experience: job.experience || '',
        location: job.location || '',
        jobType: job.jobType || ''
      });
    } else {
      setFormData({ id: '', title: '', description: '', skills: '', experience: '', location: '', jobType: '' });
    }
    setIsModalOpen(true);
  };

  const filteredJobs = jobs.filter(j => j.title.toLowerCase().includes(query.toLowerCase()));

  if (loading) return <div className="p-12 text-center"><div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div></div>;

  return (
    <div className="mx-auto max-w-[1240px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <PageHeader
        eyebrow="Requisitions"
        title="Jobs"
        description="Manage your active job postings and requirements."
        action={
          <>
            <label className="flex h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground">
              <Search size={16}/>
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search jobs" className="bg-transparent outline-none placeholder:text-muted-foreground"/>
            </label>
            <Button size="lg" onClick={() => openModal()}>
              <Plus size={16} /> Create Job
            </Button>
          </>
        }
      />

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {filteredJobs.length > 0 ? filteredJobs.map(job => (
          <article key={job.id} className="job-card">
            <div>
              <div className="flex items-start justify-between">
                <h2 className="text-lg font-bold text-foreground">{job.title}</h2>
                <div className="flex gap-1">
                  <button onClick={() => openModal(job)} className="p-1.5 text-muted-foreground hover:bg-muted rounded-md"><Edit2 size={14}/></button>
                  <button onClick={() => handleDelete(job.id)} className="p-1.5 text-destructive hover:bg-destructive/10 rounded-md"><Trash2 size={14}/></button>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                {job.location && <span className="flex items-center gap-1"><MapPin size={12}/>{job.location}</span>}
                {job.jobType && <span className="flex items-center gap-1"><Briefcase size={12}/>{job.jobType}</span>}
                {job.experience && <span className="flex items-center gap-1"><Clock size={12}/>{job.experience}</span>}
              </div>
              <p className="mt-4 line-clamp-3 text-sm text-muted-foreground">{job.description}</p>

              <div className="mt-4 flex flex-wrap gap-1">
                {job.skills?.slice(0, 4).map((skill: string) => (
                  <span key={skill} className="rounded-md bg-muted px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{skill}</span>
                ))}
                {job.skills?.length > 4 && <span className="rounded-md bg-muted px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">+{job.skills.length - 4}</span>}
              </div>
            </div>
            <div className="mt-6 border-t border-border pt-4">
              <div className="text-xs text-muted-foreground mb-3">
                Posted on {new Date(job.createdAt).toLocaleDateString()}
              </div>
              <div className="flex gap-1.5">
                <button onClick={() => alert("LinkedIn integration coming soon!")} className="flex-1 rounded border border-[#0a66c2]/30 bg-[#0a66c2]/5 py-1.5 text-[10px] font-semibold text-[#0a66c2] hover:bg-[#0a66c2]/15 transition-colors text-center whitespace-nowrap">
                  + LinkedIn
                </button>
                <button onClick={() => alert("Naukri integration coming soon!")} className="flex-1 rounded border border-[#275df5]/30 bg-[#275df5]/5 py-1.5 text-[10px] font-semibold text-[#275df5] hover:bg-[#275df5]/15 transition-colors text-center whitespace-nowrap">
                  + Naukri
                </button>
                <button onClick={() => alert("SharePoint integration coming soon!")} className="flex-1 rounded border border-[#03787c]/30 bg-[#03787c]/5 py-1.5 text-[10px] font-semibold text-[#03787c] hover:bg-[#03787c]/15 transition-colors text-center whitespace-nowrap">
                  + SharePoint
                </button>
              </div>
            </div>
          </article>
        )) : (
          <div className="col-span-full">
            <EmptyState
              icon={<Briefcase size={22} />}
              title="No jobs found"
              description="Create one to get started."
            />
          </div>
        )}
      </div>

      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{formData.id ? 'Edit Job' : 'Create Job'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-foreground">Title</label>
              <input required value={formData.title} onChange={e => setFormData({...formData, title: e.target.value})} className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm text-foreground" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-foreground">Location</label>
                <input value={formData.location} onChange={e => setFormData({...formData, location: e.target.value})} className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm text-foreground" />
              </div>
              <div>
                <label className="text-sm font-medium text-foreground">Job Type</label>
                <input value={formData.jobType} onChange={e => setFormData({...formData, jobType: e.target.value})} placeholder="e.g. Full-time" className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm text-foreground" />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Experience</label>
              <input value={formData.experience} onChange={e => setFormData({...formData, experience: e.target.value})} placeholder="e.g. 2-4 years" className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm text-foreground" />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Skills (comma separated)</label>
              <input value={formData.skills} onChange={e => setFormData({...formData, skills: e.target.value})} className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm text-foreground" />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Description</label>
              <textarea required value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} className="mt-1 w-full h-32 rounded-lg border border-border bg-background p-2 text-sm text-foreground" />
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setIsModalOpen(false)}>Cancel</Button>
              <Button type="submit">Save Job</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
