import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const field =
  "w-full rounded-xl bg-card px-3 text-sm text-ink ring-1 ring-line-2 placeholder:text-faint transition-shadow outline-none focus:ring-2 focus:ring-kb-violet/60 disabled:opacity-50";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(field, "h-9", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(field, "min-h-20 py-2 leading-relaxed resize-y", className)} {...props} />;
}
