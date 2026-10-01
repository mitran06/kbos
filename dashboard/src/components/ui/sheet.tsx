import { Dialog as D } from "radix-ui";
import type { ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export function Sheet({ open, onOpenChange, children, className, title }: { open: boolean; onOpenChange: (o: boolean) => void; children: ReactNode; className?: string; title: string }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-ink/12 backdrop-blur-[2px] data-[state=open]:animate-[fade-in_200ms_ease-out] data-[state=closed]:animate-[fade-out_150ms_ease-in]" />
        <D.Content
          aria-describedby={undefined}
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-[min(780px,94vw)] flex-col bg-bg shadow-lift outline-none",
            "data-[state=open]:animate-[sheet-in_320ms_cubic-bezier(0.22,1,0.36,1)] data-[state=closed]:animate-[sheet-out_180ms_ease-in]",
            className,
          )}
        >
          <D.Title className="sr-only">{title}</D.Title>
          {children}
          <D.Close className="absolute right-5 top-5 grid size-9 place-items-center rounded-full text-muted transition-colors hover:bg-sunk hover:text-ink cursor-pointer" aria-label="Close">
            <X className="size-5" />
          </D.Close>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
