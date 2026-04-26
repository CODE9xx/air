import Link from 'next/link';

import { Footer } from '@/components/landing/Footer';
import { Header } from '@/components/landing/Header';
import type { LegalDocument } from '@/lib/legal';

type LegalDocumentPageProps = {
  document: LegalDocument;
  locale: string;
};

function localizeHref(locale: string, href: string) {
  return `/${locale}${href}`;
}

export function LegalDocumentPage({ document, locale }: LegalDocumentPageProps) {
  return (
    <>
      <Header />
      <main className="bg-slate-50">
        <section className="container mx-auto px-4 py-12 md:py-16">
          <div className="mx-auto max-w-4xl">
            <div className="mb-8">
              <div className="text-sm font-semibold uppercase tracking-[0.18em] text-primary">
                {document.eyebrow}
              </div>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 md:text-5xl">
                {document.title}
              </h1>
              <div className="mt-4 text-sm text-slate-500">{document.updatedAt}</div>
              <div className="mt-6 space-y-4 text-base leading-7 text-slate-700">
                {document.intro.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
            </div>

            {document.related && (
              <div className="mb-8 grid gap-3 md:grid-cols-3">
                {document.related.map((item) => (
                  <Link
                    key={item.href}
                    href={localizeHref(locale, item.href)}
                    className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-primary/40 hover:shadow-md"
                  >
                    <div className="font-semibold text-slate-950">{item.title}</div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                  </Link>
                ))}
              </div>
            )}

            <div className="space-y-5">
              {document.sections.map((section) => (
                <section key={section.title} className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                  <h2 className="text-xl font-semibold text-slate-950">{section.title}</h2>
                  {section.body && (
                    <div className="mt-4 space-y-3 text-sm leading-7 text-slate-700">
                      {section.body.map((paragraph) => (
                        <p key={paragraph}>{paragraph}</p>
                      ))}
                    </div>
                  )}
                  {section.bullets && (
                    <ul className="mt-4 space-y-2 text-sm leading-7 text-slate-700">
                      {section.bullets.map((bullet) => (
                        <li key={bullet} className="flex gap-3">
                          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                          <span>{bullet}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
            </div>

            {document.disclaimer && (
              <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
                {document.disclaimer}
              </div>
            )}
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
