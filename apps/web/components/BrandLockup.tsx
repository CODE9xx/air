import { cn } from '@/lib/utils';

type BrandLockupProps = {
  className?: string;
  markClassName?: string;
  textClassName?: string;
  compact?: boolean;
};

export function BrandLockup({ className, markClassName, textClassName, compact = false }: BrandLockupProps) {
  return (
      <span className={cn('brand-lockup', className)}>
      <span className={cn('brand-mark', markClassName)} aria-hidden>
        <img
          src="/code9-logo.png"
          alt=""
          className="brand-mark-image"
        />
      </span>
      {!compact && (
        <span className={cn('brand-wordmark', textClassName)}>
          <span className="brand-wordmark-code">CODE9</span>
          <span className="brand-wordmark-analytics">ANALYTICS</span>
        </span>
      )}
    </span>
  );
}
