'use client';

import { useState, useEffect, useMemo } from 'react';
import { TrendingUp, Users, PhoneCall, Heart, CheckCircle } from 'lucide-react';
import { fetchApi } from '@/lib/api';
import { PageHeader } from '@/components/page-header';
import { StatStrip } from '@/components/stat-strip';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';

export default function AnalyticsPage() {
  const [reportData, setReportData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('daily');
  const [dateRange, setDateRange] = useState('this_month');

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchApi(`/analytics/report?period=${period}&date_range=${dateRange}`);
      setReportData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [period, dateRange]);

  const totals = useMemo(() => reportData.reduce(
    (acc, row) => ({
      candidates: acc.candidates + (row.candidates || 0),
      screened: acc.screened + (row.screened || 0),
      calls: acc.calls + (row.calls || 0),
      interested: acc.interested + (row.interested || 0),
      hired: acc.hired + (row.hired || 0),
    }),
    { candidates: 0, screened: 0, calls: 0, interested: 0, hired: 0 },
  ), [reportData]);

  const handleExport = async (format: 'csv' | 'excel') => {
    try {
      const blob = await fetchApi(`/analytics/export?report_type=${period}&format=${format}&date_range=${dateRange}`);
      if (blob) {
        const url = window.URL.createObjectURL(blob as Blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `analytics_report_${period}.${format === 'excel' ? 'xlsx' : 'csv'}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Export failed', err);
    }
  };

  if (loading && reportData.length === 0) {
    return <div className="p-12 text-center"><div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div></div>;
  }

  return (
    <div className="mx-auto max-w-[1240px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <PageHeader
        eyebrow="Deep dive"
        title="Deep Analytics"
        description="Detailed breakdown of hiring performance over time."
        action={
          <>
            <Button variant="outline" onClick={() => handleExport('csv')}>Export CSV</Button>
            <Button onClick={() => handleExport('excel')}>Export Excel</Button>
          </>
        }
      />

      <StatStrip
        items={[
          { value: totals.candidates, label: 'Candidates' },
          { value: totals.screened, label: 'Screened' },
          { value: totals.calls, label: 'Calls' },
          { value: totals.hired, label: 'Hired' },
        ]}
      />

      <div className="flex items-center gap-4 border-b border-border pb-4">
        <label className="text-sm font-medium text-foreground">Resolution:</label>
        <div className="flex rounded-lg border border-border bg-muted p-1">
          {['daily', 'weekly', 'monthly'].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-xs font-bold rounded-md capitalize ${period === p ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >
              {p}
            </button>
          ))}
        </div>

        <label className="text-sm font-medium text-foreground ml-4">Timeframe:</label>
        <Select value={dateRange} onChange={e => setDateRange(e.target.value)} className="h-9 w-auto min-w-[160px]">
          <option value="last_7_days">Last 7 Days</option>
          <option value="this_month">This Month</option>
          <option value="last_month">Last Month</option>
          <option value="this_quarter">This Quarter</option>
          <option value="this_year">This Year</option>
        </Select>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Period</TableHead>
            <TableHead><div className="flex items-center gap-1"><Users size={14}/> Candidates</div></TableHead>
            <TableHead><div className="flex items-center gap-1"><TrendingUp size={14}/> Screened</div></TableHead>
            <TableHead><div className="flex items-center gap-1"><PhoneCall size={14}/> Calls</div></TableHead>
            <TableHead><div className="flex items-center gap-1"><Heart size={14}/> Interested</div></TableHead>
            <TableHead><div className="flex items-center gap-1"><CheckCircle size={14}/> Hired</div></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reportData.length > 0 ? reportData.map((row, i) => (
            <TableRow key={i} className="font-semibold text-foreground">
              <TableCell>{row.date}</TableCell>
              <TableCell className="font-mono">{row.candidates}</TableCell>
              <TableCell className="font-mono">{row.screened}</TableCell>
              <TableCell className="font-mono">{row.calls}</TableCell>
              <TableCell className="font-mono text-primary">{row.interested}</TableCell>
              <TableCell className="font-mono text-success">{row.hired}</TableCell>
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={6} className="py-12 text-center text-muted-foreground">
                No data available for the selected period.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
