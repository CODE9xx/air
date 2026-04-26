'use client';

import { useTranslations } from 'next-intl';
import { PlayCircle } from 'lucide-react';

const lessons = ['connectCrm', 'runExport', 'readDashboard'] as const;

export default function VideoLessonsPage() {
  const t = useTranslations('cabinet.videoLessons');

  return (
    <div className="space-y-6 max-w-4xl">
      <header>
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {lessons.map((lesson) => (
          <button
            key={lesson}
            type="button"
            className="card p-5 text-left hover:border-primary/40 hover:shadow-sm transition"
            disabled
          >
            <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary">
              <PlayCircle className="h-5 w-5" />
            </div>
            <div className="font-semibold">{t(`${lesson}.title`)}</div>
            <p className="mt-2 text-sm text-muted-foreground">{t(`${lesson}.body`)}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
