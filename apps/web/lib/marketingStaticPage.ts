import fs from 'node:fs';
import path from 'node:path';

export type MarketingPageKind = 'landing' | 'pricing';

export type MarketingStaticPage = {
  css: string;
  html: string;
  script: string;
};

const FILE_BY_KIND: Record<MarketingPageKind, string> = {
  landing: 'landing.html',
  pricing: 'pricing.html',
};

export function getMarketingStaticPage(kind: MarketingPageKind, locale: string): MarketingStaticPage {
  const filePath = path.join(process.cwd(), 'content', 'marketing', FILE_BY_KIND[kind]);
  const source = fs.readFileSync(filePath, 'utf8');
  const css = extractFirst(source, /<style>([\s\S]*?)<\/style>/i);
  const body = extractFirst(source, /<body[^>]*>([\s\S]*?)<\/body>/i);
  const scripts = [...body.matchAll(/<script>([\s\S]*?)<\/script>/gi)].map((match) => match[1]);
  const html = rewriteLinks(body.replace(/<script>[\s\S]*?<\/script>/gi, ''), locale, kind);
  const script = normalizeMarketingScript(scripts.join('\n'), locale);

  return { css, html, script };
}

function extractFirst(source: string, regex: RegExp): string {
  const match = source.match(regex);
  return match?.[1] ?? '';
}

function rewriteLinks(source: string, locale: string, kind: MarketingPageKind): string {
  const rootHref = `/${locale}`;
  const pricingHref = `/${locale}/pricing`;
  const loginHref = `/${locale}/login`;
  const registerHref = `/${locale}/register`;
  const clientLoginHref = `/${locale}/client-login`;

  let html = source
    .replaceAll('src="code9-logo.png"', 'src="/code9-logo.png"')
    .replaceAll('href="главная.html"', `href="${rootHref}"`)
    .replaceAll('href="тарифы.html"', `href="${pricingHref}"`)
    .replaceAll('href="#login"', `href="${loginHref}"`)
    .replaceAll('href="#register"', `href="${registerHref}"`)
    .replaceAll('href="#terms"', `href="/${locale}/terms"`)
    .replaceAll('href="#privacy"', `href="/${locale}/privacy"`)
    .replaceAll('href="#personal-data"', `href="/${locale}/personal-data"`);

  if (kind === 'landing') {
    html = html.replace('href="#" class="c9-logo"', `href="${rootHref}" class="c9-logo"`);
    html = html.replaceAll(`href="${pricingHref}" class="btn btn-primary"`, `href="${pricingHref}" class="btn btn-primary"`);
  }

  if (kind === 'pricing') {
    html = html.replaceAll('href="https://analytics.aicode9.ru/"', `href="${clientLoginHref}"`);
  }

  return html;
}

function normalizeMarketingScript(source: string, locale: string): string {
  return source
    .replaceAll("localStorage.getItem('code9-theme')||'dark'", "localStorage.getItem('code9-theme')||localStorage.getItem('code9_theme')||'dark'")
    .replaceAll("localStorage.setItem('code9-theme', next);", "localStorage.setItem('code9-theme', next); localStorage.setItem('code9_theme', next); document.documentElement.classList.toggle('dark', next === 'dark');")
    .replaceAll("const saved = localStorage.getItem('code9-lang') || 'ru';", `const saved = '${locale}' || localStorage.getItem('code9-lang') || 'ru';`);
}
