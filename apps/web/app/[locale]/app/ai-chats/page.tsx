'use client';

import Link from 'next/link';
import { useLocale } from 'next-intl';
import {
  BookOpen,
  CheckCircle2,
  Database,
  Mail,
  MessageSquareText,
  ShieldCheck,
} from 'lucide-react';
import { Badge } from '@/components/ui/Badge';

const COPY = {
  ru: {
    badge: 'Скоро после настройки',
    title: 'AI-чаты',
    subtitle:
      'Здесь будут AI-чаты по данным клиента: вопросы к базе знаний, истории сделок, письмам, звонкам и перепискам.',
    setupTitle: 'Что нужно настроить',
    setup: [
      'Подключить amoCRM и выгрузить сделки, контакты и компании.',
      'Подключить почту, чаты или телефонию, если AI должен отвечать по коммуникациям.',
      'Собрать базу знаний клиента и разрешить AI-обработку внутри tenant schema.',
    ],
    modesTitle: 'Какие чаты будут',
    modes: [
      ['Чат владельца', 'Сводки по продажам, рискам, менеджерам и деньгам.'],
      ['Чат РОПа', 'Контроль сделок, просрочек, воронок и задач менеджеров.'],
      ['Чат менеджера', 'Подсказки по конкретной сделке и истории клиента.'],
      ['Чат поддержки', 'Ответы по базе знаний, письмам и перепискам клиента.'],
    ],
    safetyTitle: 'Безопасность',
    safety:
      'AI-чаты будут работать только внутри данных конкретного клиента. Cross-client dataset и обучение на чужих данных не включаются.',
    primary: 'Настроить подключения',
    secondary: 'База знаний',
  },
  en: {
    badge: 'Coming after setup',
    title: 'AI chats',
    subtitle:
      'AI chats over customer data: knowledge base, deal history, emails, calls and messages.',
    setupTitle: 'Required setup',
    setup: [
      'Connect amoCRM and export deals, contacts and companies.',
      'Connect email, chats or telephony if AI should answer using communications.',
      'Build the client knowledge base and allow AI processing inside the tenant schema.',
    ],
    modesTitle: 'Planned chat modes',
    modes: [
      ['Owner chat', 'Sales, risks, managers and revenue summaries.'],
      ['Head of Sales chat', 'Deal, overdue task, pipeline and manager control.'],
      ['Manager chat', 'Hints for a specific deal and client history.'],
      ['Support chat', 'Answers from the knowledge base, emails and messages.'],
    ],
    safetyTitle: 'Security',
    safety:
      'AI chats will work only inside one customer tenant. Cross-client datasets and training on other customers are not enabled.',
    primary: 'Configure connections',
    secondary: 'Knowledge base',
  },
  es: {
    badge: 'Próximamente tras configurar',
    title: 'Chats IA',
    subtitle:
      'Chats IA sobre datos del cliente: base de conocimiento, deals, emails, llamadas y mensajes.',
    setupTitle: 'Configuración necesaria',
    setup: [
      'Conectar amoCRM y exportar deals, contactos y empresas.',
      'Conectar email, chats o telefonía si la IA debe responder usando comunicaciones.',
      'Crear la base de conocimiento del cliente y permitir procesamiento IA dentro del tenant schema.',
    ],
    modesTitle: 'Modos de chat previstos',
    modes: [
      ['Chat del dueño', 'Resumen de ventas, riesgos, managers e ingresos.'],
      ['Chat del director comercial', 'Control de deals, tareas vencidas, embudos y managers.'],
      ['Chat del manager', 'Consejos por deal e historial del cliente.'],
      ['Chat de soporte', 'Respuestas desde base de conocimiento, emails y mensajes.'],
    ],
    safetyTitle: 'Seguridad',
    safety:
      'Los chats IA funcionarán solo dentro del tenant del cliente. No se activan datasets entre clientes ni entrenamiento con datos ajenos.',
    primary: 'Configurar conexiones',
    secondary: 'Base de conocimiento',
  },
};

export default function AiChatsPage() {
  const locale = useLocale();
  const copy = COPY[locale as keyof typeof COPY] ?? COPY.ru;

  return (
    <div className="space-y-6">
      <header className="cabinet-page-hero rounded-2xl border border-border p-6">
        <Badge tone="info">{copy.badge}</Badge>
        <div className="mt-4 flex items-start gap-4">
          <div className="rounded-2xl bg-primary/10 p-3 text-primary">
            <MessageSquareText className="h-7 w-7" />
          </div>
          <div className="max-w-3xl">
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">{copy.title}</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.subtitle}</p>
          </div>
        </div>
      </header>

      <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="card p-5">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">{copy.setupTitle}</h2>
          </div>
          <ul className="mt-4 space-y-3">
            {copy.setup.map((item) => (
              <li key={item} className="flex gap-3 text-sm leading-6 text-muted-foreground">
                <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-primary" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card p-5">
          <div className="flex items-center gap-2">
            <MessageSquareText className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">{copy.modesTitle}</h2>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {copy.modes.map(([title, body]) => (
              <div key={title} className="rounded-xl border border-border bg-white p-4">
                <div className="font-semibold text-foreground">{title}</div>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="card border-primary/30 bg-primary/5 p-5">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <h2 className="text-lg font-semibold">{copy.safetyTitle}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.safety}</p>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link href={`/${locale}/app/connections`} className="btn-primary inline-flex items-center gap-2">
            <Mail className="h-4 w-4" />
            {copy.primary}
          </Link>
          <Link href={`/${locale}/app/knowledge-base`} className="btn-secondary inline-flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            {copy.secondary}
          </Link>
        </div>
      </section>
    </div>
  );
}
