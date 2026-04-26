'use client';

import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronsDown, Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/utils';

type Theme = 'light' | 'dark';

const STORAGE_KEY = 'code9_theme';
const PULL_LIMIT = 34;
const PULL_THRESHOLD = 12;

function readTheme(): Theme {
  if (typeof document === 'undefined') return 'light';
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Theme still changes for the current page if storage is unavailable.
  }
}

export function PullChainThemeToggle({ className }: { className?: string }) {
  const t = useTranslations('common');
  const [theme, setTheme] = useState<Theme>('light');
  const [pull, setPull] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startY = useRef(0);
  const pullRef = useRef(0);
  const pointerId = useRef<number | null>(null);

  useEffect(() => {
    setTheme(readTheme());
  }, []);

  const toggleTheme = () => {
    const nextTheme = readTheme() === 'dark' ? 'light' : 'dark';
    applyTheme(nextTheme);
    setTheme(nextTheme);
  };

  const onPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    pointerId.current = event.pointerId;
    startY.current = event.clientY;
    pullRef.current = 0;
    setDragging(true);
    setPull(0);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    if (!dragging || pointerId.current !== event.pointerId) return;
    const nextPull = Math.max(0, Math.min(PULL_LIMIT, event.clientY - startY.current));
    pullRef.current = nextPull;
    setPull(nextPull);
  };

  const finishPull = (event: PointerEvent<HTMLButtonElement>) => {
    if (!dragging || pointerId.current !== event.pointerId) return;
    const shouldToggle = pullRef.current >= PULL_THRESHOLD;
    pointerId.current = null;
    pullRef.current = 0;
    setDragging(false);
    setPull(0);
    if (shouldToggle) toggleTheme();
  };

  const label = theme === 'dark' ? t('themeLight') : t('themeDark');

  return (
    <button
      type="button"
      className={cn('theme-chain-toggle', theme === 'dark' && 'is-dark', dragging && 'is-pulling', className)}
      style={{ '--chain-pull': `${pull}px` } as CSSProperties}
      aria-label={label}
      title={label}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finishPull}
      onPointerCancel={finishPull}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          toggleTheme();
        }
      }}
    >
      <span className="theme-lamp-head" aria-hidden>
        <span className="theme-lamp-glow" />
        <span className="theme-lamp-icon">
          {theme === 'dark' ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
        </span>
      </span>
      <span className="theme-chain-pull" aria-hidden>
        <span className="theme-chain-beads" />
        <span className="theme-chain-handle">
          <ChevronsDown className="h-3 w-3" />
        </span>
      </span>
    </button>
  );
}
