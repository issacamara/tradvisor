import React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean };

export function Button({ asChild, className, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn("inline-flex min-h-10 items-center justify-center rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink hover:bg-white/10", className)} {...props} />;
}
