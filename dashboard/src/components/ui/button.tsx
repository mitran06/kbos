import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-medium transition-[background-color,color,box-shadow,transform] duration-150 ease-out active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0 cursor-pointer select-none",
  {
    variants: {
      variant: {
        default: "bg-ink text-white hover:bg-ink/88 shadow-[0_1px_2px_rgba(0,0,0,.12)]",
        outline: "bg-card text-ink ring-1 ring-line-2 hover:bg-sunk",
        ghost: "text-ink-2 hover:bg-sunk hover:text-ink",
        danger: "bg-crit text-white hover:bg-crit/90",
        dangerSoft: "bg-crit-soft text-crit ring-1 ring-crit/15 hover:bg-crit/12",
      },
      size: {
        sm: "h-8 px-3 text-[0.8125rem]",
        md: "h-9 px-4 text-sm",
        lg: "h-11 px-5 text-[0.9375rem]",
        icon: "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export function Button({ className, variant, size, type = "button", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
