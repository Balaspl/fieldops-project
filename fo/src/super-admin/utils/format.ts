export const text = (value: any, fallback = '—') => value === null || value === undefined || value === '' ? fallback : String(value);
export const statusLabel = (value: any) => text(value, 'UNKNOWN').replace(/[_-]+/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
export const statusTone = (value: any): 'green' | 'red' | 'amber' | 'blue' | 'purple' | 'neutral' => {
  const s = String(value || '').toUpperCase();
  if (['AVAILABLE', 'ONLINE', 'COMPLETED', 'CLOSED', 'RESOLVED', 'ACTIVE', 'ACCEPTED', 'ALL', 'ALL STATUSES', 'ALL SLA', 'LOW'].includes(s)) return 'green';
  if (['OFFLINE', 'CANCELLED', 'CANCELED', 'FAILED', 'REJECTED', 'CRITICAL', 'URGENT', 'BREACHED'].includes(s)) return 'red';
  if (['PENDING', 'QUEUED', 'CREATED', 'OPEN', 'WAITING', 'AWAITING ACCEPTANCE', 'HIGH'].includes(s)) return 'amber';
  if (['ASSIGNED', 'EN_ROUTE', 'ENROUTE', 'IN_PROGRESS', 'ON_SITE', 'MEDIUM', 'MEDIUM PRIORITY'].includes(s)) return 'blue';
  if (['ESCALATED', 'ESCALATED_TO_CTO'].includes(s)) return 'purple';
  return 'neutral';
};
export const dateTime = (value?: string | null) => {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
};
export const timeAgo = (value?: string | null) => {
  if (!value) return 'No recent GPS';
  const stamp = new Date(value).getTime();
  if (!Number.isFinite(stamp)) return 'Unknown';
  const minutes = Math.max(0, Math.floor((Date.now() - stamp) / 60000));
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} hr ago`;
  return `${Math.floor(minutes / 1440)} day(s) ago`;
};
export const currency = (value: any) => {
  const amount = Number(value);
  return Number.isFinite(amount) ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(amount) : '—';
};
export const initials = (name?: string) => String(name || 'FO').trim().split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
