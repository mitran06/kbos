import { Popover as P } from "radix-ui";
import type { ReactNode } from "react";

export function Popover({ trigger, children, open, onOpenChange }: { trigger: ReactNode; children: ReactNode; open?: boolean; onOpenChange?: (o: boolean) => void }) {
  return (
    <P.Root open={open} onOpenChange={onOpenChange}>
      <P.Trigger asChild>{trigger}</P.Trigger>
      <P.Portal>
        <P.Content align="start" sideOffset={8} className="z-[60] w-72 rounded-2xl bg-card p-1.5 shadow-lift ring-1 ring-line outline-none data-[state=open]:animate-[menu-in_140ms_ease-out]">
          {children}
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}
