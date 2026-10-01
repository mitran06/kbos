import { Dialog as D } from "radix-ui";
import type { ReactNode } from "react";

export function Dialog({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-ink/20 backdrop-blur-[2px] data-[state=open]:animate-[fade-in_180ms_ease-out]" />
        <D.Content className="fixed left-1/2 top-1/2 z-50 w-[min(460px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-3xl bg-card p-7 shadow-lift outline-none data-[state=open]:animate-[pop-in_220ms_cubic-bezier(0.22,1,0.36,1)]">
          <D.Title className="text-lg font-semibold tracking-tight">{title}</D.Title>
          {description ? <D.Description className="mt-2 text-sm leading-relaxed text-ink-2">{description}</D.Description> : null}
          <div className="mt-6">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
export const DialogClose = D.Close;
