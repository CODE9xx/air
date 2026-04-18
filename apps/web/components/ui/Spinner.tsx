import { cn } from '@/lib/utils';

export function Spinner({ className, size = 16 }: { className?: string; size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={cn(
        'inline-block animate-spin rounded-full border-2 border-primary border-t-transparent',
        className,
      )}
    />
  );
}
