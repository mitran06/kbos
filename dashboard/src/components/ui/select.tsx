import { Select as S } from "radix-ui";
import { Check, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface Option<V extends string> {
  value: V;
  label: ReactNode;
}

export function Select<V extends string>({ value, onChange, options, className, label, disabled }: { value: V; onChange: (v: V) => void; options: Option<V>[]; className?: string; label: string; disabled?: boolean }) {
  return (
    <S.Root value={value} onValueChange={(v) => onChange(v as V)} disabled={disabled}>
      <S.Trigger
        aria-label={label}
        className={cn(
          "inline-flex h-9 items-center justify-between gap-2 rounded-full bg-card pl-3.5 pr-2.5 text-sm text-ink ring-1 ring-line-2 outline-none transition-colors hover:bg-sunk focus-visible:ring-2 focus-visible:ring-kb-violet/60 data-[disabled]:opacity-50 cursor-pointer",
          className,
        )}
      >
        <S.Value />
        <S.Icon>
          <ChevronDown className="size-4 text-muted" />
        </S.Icon>
      </S.Trigger>
      <S.Portal>
        <S.Content position="popper" sideOffset={6} className="z-[60] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-2xl bg-card p-1.5 shadow-lift ring-1 ring-line data-[state=open]:animate-[menu-in_140ms_ease-out]">
          <S.Viewport>
            {options.map((o) => (
              <S.Item
                key={o.value}
                value={o.value}
                className="relative flex h-9 cursor-pointer select-none items-center rounded-xl pl-3 pr-8 text-sm text-ink outline-none data-[highlighted]:bg-sunk"
              >
                <S.ItemText>{o.label}</S.ItemText>
                <S.ItemIndicator className="absolute right-2.5">
                  <Check className="size-4" />
                </S.ItemIndicator>
              </S.Item>
            ))}
          </S.Viewport>
        </S.Content>
      </S.Portal>
    </S.Root>
  );
}
