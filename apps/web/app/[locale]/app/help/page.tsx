'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { LifeBuoy, Mail, MessageCircle } from 'lucide-react';

const channels = [
  { key: 'telegram', icon: MessageCircle, href: 'https://t.me/aicode9' },
  { key: 'email', icon: Mail, href: 'mailto:support@aicode9.ru' },
] as const;

export default function HelpPage() {
  const t = useTranslations('cabinet.help');

  return (
    <div className="space-y-6 max-w-4xl">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      <div className="card p-6">
        <div className="flex items-start gap-4">
          <div className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <LifeBuoy className="h-5 w-5" />
          </div>
          <div>
            <h2 className="font-semibold">{t('supportTitle')}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t('supportBody')}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {channels.map(({ key, icon: Icon, href }) => (
          <Link
            key={key}
            href={href}
            target={href.startsWith('http') ? '_blank' : undefined}
            rel={href.startsWith('http') ? 'noreferrer' : undefined}
            className="card p-5 flex items-center gap-3 hover:border-primary/40 hover:shadow-sm transition"
          >
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-muted text-muted-foreground">
              <Icon className="h-5 w-5" />
            </span>
            <span>
              <span className="block font-semibold">{t(`${key}.title`)}</span>
              <span className="block text-sm text-muted-foreground">{t(`${key}.body`)}</span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
