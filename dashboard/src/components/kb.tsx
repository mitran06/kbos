import { AlertTriangle, CircleCheck, CircleDot, Clock3, HelpCircle, Loader } from "lucide-react";
import type { ReactNode } from "react";
import { SEVERITY_LABEL, isOverdue } from "@/lib/format";
import type { Severity, Status, TicketSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

/** KB's identity: a soft multicolor orb. Used sparingly. */
export function Orb({ size = 28, className, still = false }: { size?: number; className?: string; still?: boolean }) {
  return (
    <span className={cn("relative inline-block shrink-0 rounded-full", className)} style={{ width: size, height: size }} aria-hidden>
      <span
        className={cn("absolute inset-0 rounded-full", !still && "animate-orb")}
        style={{
          background:
            "radial-gradient(circle at 30% 28%, rgba(255,255,255,.95) 0 12%, transparent 38%), conic-gradient(from 200deg, var(--color-kb-blue), var(--color-kb-violet), var(--color-kb-pink), var(--color-kb-teal), var(--color-kb-blue))",
          filter: "saturate(1.05)",
        }}
      />
      <span className="absolute inset-0 rounded-full shadow-[inset_0_-2px_6px_rgba(80,60,160,.18),0_2px_10px_-2px_rgba(140,120,250,.45)]" />
    </span>
  );
}

interface AvatarPerson {
  name: string;
  initials: string;
  avatar_hue: number;
}

export function Avatar({ person, size = 28, ring = false, className }: { person: AvatarPerson; size?: number; ring?: boolean; className?: string }) {
  const h = person.avatar_hue;
  return (
    <span
      title={person.name}
      className={cn("inline-grid shrink-0 place-items-center rounded-full font-semibold tracking-tight", ring && "ring-2 ring-card", className)}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: `linear-gradient(140deg, hsl(${h} 85% 90%), hsl(${(h + 35) % 360} 70% 80%))`,
        color: `hsl(${h} 45% 28%)`,
      }}
    >
      {person.initials}
    </span>
  );
}

export function AvatarStack({ people, size = 28, max = 3 }: { people: AvatarPerson[]; size?: number; max?: number }) {
  if (!people.length) return <span className="text-sm text-faint">Unassigned</span>;
  const shown = people.slice(0, max);
  return (
    <span className="flex items-center">
      {shown.map((p, i) => (
        <Avatar key={p.name} person={p} size={size} ring className={i ? "-ml-1.5" : ""} />
      ))}
      {people.length > max ? <span className="-ml-1.5 grid place-items-center rounded-full bg-sunk px-1.5 text-xs text-ink-2 ring-2 ring-card" style={{ height: size }}>+{people.length - max}</span> : null}
    </span>
  );
}

export function Pill({ className, children, title }: { className?: string; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-[0.78rem] font-medium leading-none", className)}>
      {children}
    </span>
  );
}

const SEV_STYLE: Record<Severity, { pill: string; dot: string }> = {
  critical: { pill: "bg-crit-soft text-crit", dot: "bg-crit" },
  high: { pill: "bg-high-soft text-high", dot: "bg-high" },
  medium: { pill: "bg-sunk text-ink-2", dot: "bg-ink-2/60" },
  low: { pill: "bg-sunk text-muted", dot: "bg-faint" },
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const s = SEV_STYLE[severity];
  return (
    <Pill className={cn(s.pill, className)}>
      <span className={cn("size-1.5 rounded-full", s.dot)} />
      {SEVERITY_LABEL[severity]}
    </Pill>
  );
}

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  switch (status) {
    case "open":
      return (
        <Pill className={cn("bg-card text-ink ring-1 ring-line-2", className)}>
          <CircleDot className="size-3.5 text-ink-2" /> Open
        </Pill>
      );
    case "in_progress":
      return (
        <Pill className={cn("bg-card text-ink ring-1 ring-line-2", className)}>
          <Loader className="size-3.5 text-ink-2" /> In Progress
        </Pill>
      );
    case "monitoring":
      return (
        <Pill className={cn("bg-amber-soft text-amber ring-1 ring-amber-line/70", className)} title="Monitoring never means resolved">
          <Clock3 className="size-3.5" /> Monitoring <span className="font-normal opacity-75">· not resolved</span>
        </Pill>
      );
    case "closed":
      return (
        <Pill className={cn("bg-ok-soft text-ok", className)}>
          <CircleCheck className="size-3.5" /> Closed
        </Pill>
      );
  }
}

export function OverdueBadge({ className }: { className?: string }) {
  return (
    <Pill className={cn("bg-crit text-white", className)} title="The next check time has passed">
      <AlertTriangle className="size-3.5" /> Overdue
    </Pill>
  );
}

export function UnclearBadge({ className, label = "Unclear check" }: { className?: string; label?: string }) {
  return (
    <Pill className={cn("bg-amber-soft text-amber ring-1 ring-amber-line", className)} title="A Check that doesn't say what was checked or found">
      <HelpCircle className="size-3.5" /> {label}
    </Pill>
  );
}

export function TicketStatusBadges({ t, now }: { t: TicketSummary; now: number }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <StatusBadge status={t.status} />
      {isOverdue(t, now) ? <OverdueBadge /> : null}
      {t.unclear && t.status !== "closed" ? <UnclearBadge /> : null}
    </span>
  );
}

export function MachineChip({ code, className }: { code: string; className?: string }) {
  return (
    <span className={cn("inline-grid h-7 min-w-9 place-items-center rounded-lg bg-sunk px-1.5 font-mono text-[0.8rem] font-semibold tracking-tight text-ink ring-1 ring-line", className)}>
      {code}
    </span>
  );
}

export function KeyChip({ k, onClick, className }: { k: string; onClick?: () => void; className?: string }) {
  const cls = cn("inline-flex h-7 items-center rounded-full bg-card px-2.5 font-mono text-[0.78rem] font-medium text-ink ring-1 ring-line-2 tnum", onClick && "cursor-pointer transition-colors hover:bg-sunk hover:ring-ink/20", className);
  return onClick ? (
    <button type="button" onClick={onClick} className={cls}>
      {k}
    </button>
  ) : (
    <span className={cls}>{k}</span>
  );
}
