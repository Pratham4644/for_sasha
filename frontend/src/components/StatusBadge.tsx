import React from 'react';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md' }) => {
  const s = status.toUpperCase();

  let bg = 'bg-slate-800 text-slate-300 border-slate-700';
  let dot = 'bg-slate-400';

  if (s === 'ONLINE' || s === 'ACTIVE') {
    bg = 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60';
    dot = 'bg-emerald-400 animate-pulse';
  } else if (s === 'DEGRADED' || s === 'STARTING') {
    bg = 'bg-amber-950/60 text-amber-400 border-amber-800/60';
    dot = 'bg-amber-400 animate-pulse';
  } else if (s === 'OFFLINE' || s === 'STOPPING') {
    bg = 'bg-rose-950/60 text-rose-400 border-rose-800/60';
    dot = 'bg-rose-400';
  } else if (s === 'ERROR') {
    bg = 'bg-red-950/80 text-red-300 border-red-700';
    dot = 'bg-red-500';
  } else if (s === 'DISABLED' || s === 'INACTIVE') {
    bg = 'bg-slate-900 text-slate-500 border-slate-800';
    dot = 'bg-slate-600';
  }

  const px = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-medium border ${bg} ${px}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {s}
    </span>
  );
};
