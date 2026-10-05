import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: number | string;
  icon: LucideIcon;
  subtitle?: string;
  color?: 'emerald' | 'blue' | 'amber' | 'rose' | 'slate';
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  icon: Icon,
  subtitle,
  color = 'slate',
}) => {
  const colorMap = {
    emerald: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/40',
    blue: 'text-blue-400 bg-blue-950/40 border-blue-800/40',
    amber: 'text-amber-400 bg-amber-950/40 border-amber-800/40',
    rose: 'text-rose-400 bg-rose-950/40 border-rose-800/40',
    slate: 'text-slate-300 bg-slate-900/60 border-slate-800',
  };

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 shadow-sm hover:border-slate-700/80 transition-colors">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-400">{title}</p>
        <div className={`p-2.5 rounded-lg border ${colorMap[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div className="mt-3">
        <h3 className="text-2xl font-bold text-slate-100 tracking-tight">{value}</h3>
        {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
      </div>
    </div>
  );
};
