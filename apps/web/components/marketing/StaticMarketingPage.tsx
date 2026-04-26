'use client';

import { useEffect } from 'react';

type StaticMarketingPageProps = {
  css: string;
  html: string;
  script: string;
  locale: string;
  page: 'landing' | 'pricing';
};

type MarketingWindow = Window & {
  __CODE9_LOCALE__?: string;
};

export function StaticMarketingPage({ css, html, script, locale, page }: StaticMarketingPageProps) {
  useEffect(() => {
    const win = window as MarketingWindow;
    win.__CODE9_LOCALE__ = locale;

    try {
      const storedTheme = localStorage.getItem('code9-theme') || localStorage.getItem('code9_theme') || 'dark';
      document.documentElement.setAttribute('data-theme', storedTheme);
      document.documentElement.classList.toggle('dark', storedTheme === 'dark');
      localStorage.setItem('code9-theme', storedTheme);
      localStorage.setItem('code9_theme', storedTheme);
      localStorage.setItem('code9-lang', locale);
    } catch (_) {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.documentElement.classList.add('dark');
    }

    if (script.trim()) {
      Function(script)();
    }

    const languageButtons = Array.from(document.querySelectorAll<HTMLButtonElement>('.lang-item[data-lang]'));
    const handlers = languageButtons.map((button) => {
      const handler = () => {
        const nextLocale = button.dataset.lang;
        if (!nextLocale || nextLocale === locale) return;
        try {
          localStorage.setItem('code9-lang', nextLocale);
        } catch (_) {}
        window.location.assign(`/${nextLocale}${page === 'pricing' ? '/pricing' : ''}`);
      };
      button.addEventListener('click', handler);
      return () => button.removeEventListener('click', handler);
    });

    return () => {
      handlers.forEach((cleanup) => cleanup());
    };
  }, [locale, page, script]);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="code9-marketing-static" dangerouslySetInnerHTML={{ __html: html }} />
    </>
  );
}
