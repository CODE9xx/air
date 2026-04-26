'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  Check,
  CreditCard,
  DatabaseZap,
  FileText,
  MessageSquareText,
  ReceiptText,
  ShieldCheck,
  Sparkles,
  WalletCards,
} from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import type { BillingAccount, PaymentCreateResponse, TokenAccount } from '@/lib/types';
import { getPricingPlans, type PricingPlan, type PricingPeriodKey } from '@/lib/pricing';
import { cn, formatNumber, toIntlLocale } from '@/lib/utils';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';

type ModuleKey = 'knowledge_bot' | 'ai_rop' | 'auto_actions' | 'speech_analytics';
type TokenPackKey = 'none' | 'tokens_10000' | 'tokens_25000' | 'tokens_50000' | 'tokens_100000';
type SlaKey = 'priority_queue' | 'sla' | 'private_contour';

interface AddonItem<Key extends string = string> {
  key: Key;
  name: string;
  description: string;
  price: number;
  custom?: boolean;
  defaultActive?: boolean;
}

interface LocalCopy {
  constructorTitle: string;
  constructorBody: string;
  includedBadge: string;
  includedBody: string;
  currentPlan: string;
  notSelected: string;
  includedTokens: string;
  availableTokens: string;
  safeMode: string;
  stepServer: string;
  stepServerBody: string;
  largeTeamHint: string;
  stepModules: string;
  stepModulesBody: string;
  stepTokens: string;
  stepTokensBody: string;
  tokenBillingHint: string;
  stepUsage: string;
  stepUsageBody: string;
  stepSla: string;
  stepSlaBody: string;
  summaryTitle: string;
  month: string;
  six: string;
  year: string;
  total: string;
  perMonth: string;
  selected: string;
  choosePlan: string;
  collectPlan: string;
  requestQuote: string;
  disabledTitle: string;
  disabledBody: string;
  noAddons: string;
  noTokens: string;
  noSla: string;
  byContract: string;
  economy: string;
  payForPeriod: string;
  tokensIncluded: string;
  users: string;
  update: string;
  allTariffs: string;
  aiUsers: string;
  callMinutes: string;
  usageGroups: Array<{ title: string; rows: Array<[string, string]> }>;
  formulaTitle: string;
  formulaBody: string;
  formulaRows: Array<[string, string, string]>;
}

const COPY: Record<'ru' | 'en' | 'es', LocalCopy> = {
  ru: {
    constructorTitle: 'Конструктор тарифа CODE9',
    constructorBody:
      'Соберите тариф под свой отдел продаж: выберите сервер, AI-модули, дополнительные токены и SLA. Это тот же принцип, что на главной тарифной странице.',
    includedBadge: 'Включено во все тарифы',
    includedBody:
      'База знаний, транскрибация звонков 1,5 токена/мин, базовые роли, подключение CRM и безопасный кабинет.',
    currentPlan: 'Текущий тариф',
    notSelected: 'Не выбран',
    includedTokens: 'Включено токенов',
    availableTokens: 'Доступно токенов',
    safeMode: 'Оплата через Т-Банк',
    stepServer: '1. Выберите сервер',
    stepServerBody: 'Базовая конфигурация: AI-токены, пользователи и частота обновления базы.',
    largeTeamHint:
      'amoCRM ограничивает интеграции 7 запросами в секунду. Для отделов от 30 менеджеров лучше Enterprise Server + приоритетная очередь.',
    stepModules: '2. Добавьте AI-модули',
    stepModulesBody: 'Подключаемые возможности для отдела продаж.',
    stepTokens: '3. Дополнительные токены',
    stepTokensBody: 'Токены расходуются на звонки, чаты, письма, обновления базы и AI-задачи.',
    tokenBillingHint: 'Списания идут за каждое AI-действие и анализ звонков. Подробный прайс ниже.',
    stepUsage: 'Сколько токенов за каждое действие',
    stepUsageBody: 'Прозрачная тарификация: цена AI-действий фиксирована.',
    stepSla: '4. SLA и инфраструктура',
    stepSlaBody: 'Дополнительные гарантии, выделенные ресурсы и приватный контур.',
    summaryTitle: 'Ваш тариф',
    month: '1 месяц',
    six: '6 месяцев −10%',
    year: '12 месяцев −20%',
    total: 'Итого',
    perMonth: '/ мес',
    selected: 'Выбран',
    choosePlan: 'Выбрать',
    collectPlan: 'Собрать тариф',
    requestQuote: 'Запросить расчёт',
    disabledTitle: 'Платежи пока выключены',
    disabledBody: 'Это безопасный UI-этап. Реальная покупка тарифа и списание будут включены отдельным GO.',
    noAddons: 'AI-модули не выбраны',
    noTokens: 'Доп. токены не выбраны',
    noSla: 'SLA не выбран',
    byContract: 'по договору',
    economy: 'экономия',
    payForPeriod: 'к оплате за период',
    tokensIncluded: 'AI-токенов включено',
    users: 'AI-пользователей',
    update: 'Обновление',
    allTariffs: 'Также во все тарифы входит база знаний и базовая транскрибация.',
    aiUsers: 'AI-пользователей',
    callMinutes: 'мин/мес звонков',
    usageGroups: [
      {
        title: 'Звонки',
        rows: [
          ['Транскрибация', '1,5 токена / мин'],
          ['Анализ звонка: эмоции, скрипт, итоги', '5 токенов'],
          ['Речевая аналитика: развёрнутый отчёт', '10 токенов'],
        ],
      },
      {
        title: 'Коммуникации',
        rows: [
          ['Ответ в чате', '2 токена'],
          ['AI-письмо / автоответ', '3 токена'],
          ['Сложный ответ по базе знаний', '5 токенов'],
        ],
      },
      {
        title: 'Автодействия',
        rows: [
          ['Постановка задачи', '1 токен'],
          ['Напоминание', '1 токен'],
          ['Перевод сделки по воронке', '1 токен'],
          ['Формирование счёта', '2 токена'],
        ],
      },
      {
        title: 'AI-РОП',
        rows: [
          ['Анализ одной сделки', '5 токенов'],
          ['Анализ всей истории клиента', '20–30 токенов'],
          ['Ежедневный скан отдела на 1 менеджера', '5 токенов'],
        ],
      },
    ],
    formulaTitle: 'Как считать объём',
    formulaBody:
      '1 AIC9 токен примерно равен 1 000 LLM-токенов обработки AI. Чем больше писем, чатов и расшифровок читает AI, тем больше списание.',
    formulaRows: [
      ['Звонки, расшифровки', '5 × ~2 000', '~10 000'],
      ['Чаты клиента', '30 × ~200', '~6 000'],
      ['Письма', '10 × ~500', '~5 000'],
      ['Промпт AI + отчёт', '~4 000', '~4 000'],
    ],
  },
  en: {
    constructorTitle: 'CODE9 plan builder',
    constructorBody:
      'Build a plan for your sales team: choose a server, AI modules, extra tokens and SLA. This mirrors the public pricing constructor.',
    includedBadge: 'Included in every plan',
    includedBody:
      'Knowledge base, call transcription at 1.5 tokens/min, base roles, CRM connection and secure cabinet.',
    currentPlan: 'Current plan',
    notSelected: 'Not selected',
    includedTokens: 'Included tokens',
    availableTokens: 'Available tokens',
    safeMode: 'T-Bank payments',
    stepServer: '1. Choose server',
    stepServerBody: 'Base configuration: AI tokens, users and database refresh frequency.',
    largeTeamHint:
      'amoCRM limits integrations to 7 requests per second. For teams from 30 managers, use Enterprise Server + priority queue.',
    stepModules: '2. Add AI modules',
    stepModulesBody: 'Optional capabilities for the sales department.',
    stepTokens: '3. Extra tokens',
    stepTokensBody: 'Tokens are spent on calls, chats, emails, base updates and AI tasks.',
    tokenBillingHint: 'Charges happen per AI action and call analysis. Detailed rates are below.',
    stepUsage: 'Token rates per action',
    stepUsageBody: 'Transparent pricing: AI action rates are fixed.',
    stepSla: '4. SLA and infrastructure',
    stepSlaBody: 'Additional guarantees, dedicated resources and private setup.',
    summaryTitle: 'Your plan',
    month: '1 month',
    six: '6 months −10%',
    year: '12 months −20%',
    total: 'Total',
    perMonth: '/ mo',
    selected: 'Selected',
    choosePlan: 'Choose',
    collectPlan: 'Build plan',
    requestQuote: 'Request quote',
    disabledTitle: 'Payments are disabled',
    disabledBody: 'This is a safe UI phase. Real purchase and charging will be enabled with a separate GO.',
    noAddons: 'No AI modules selected',
    noTokens: 'No extra tokens selected',
    noSla: 'No SLA selected',
    byContract: 'by contract',
    economy: 'saving',
    payForPeriod: 'to pay for period',
    tokensIncluded: 'AI tokens included',
    users: 'AI users',
    update: 'Refresh',
    allTariffs: 'Knowledge base and basic transcription are included in every plan.',
    aiUsers: 'AI users',
    callMinutes: 'call min/mo',
    usageGroups: [
      { title: 'Calls', rows: [['Transcription', '1.5 tokens / min'], ['Call analysis', '5 tokens'], ['Speech analytics report', '10 tokens']] },
      { title: 'Communications', rows: [['Chat reply', '2 tokens'], ['AI email / autoresponse', '3 tokens'], ['Complex knowledge-base answer', '5 tokens']] },
      { title: 'Auto-actions', rows: [['Create task', '1 token'], ['Reminder', '1 token'], ['Move deal in funnel', '1 token'], ['Invoice generation', '2 tokens']] },
      { title: 'AI Head of Sales', rows: [['One deal analysis', '5 tokens'], ['Whole client history', '20–30 tokens'], ['Daily scan per manager', '5 tokens']] },
    ],
    formulaTitle: 'How volume is calculated',
    formulaBody:
      '1 AIC9 token is roughly 1,000 LLM processing tokens. The more emails, chats and transcripts AI reads, the higher the charge.',
    formulaRows: [['Call transcripts', '5 × ~2,000', '~10,000'], ['Client chats', '30 × ~200', '~6,000'], ['Emails', '10 × ~500', '~5,000'], ['AI prompt + report', '~4,000', '~4,000']],
  },
  es: {
    constructorTitle: 'Constructor de tarifa CODE9',
    constructorBody:
      'Configura una tarifa para tu equipo de ventas: servidor, módulos IA, tokens extra y SLA. Es el mismo principio que en la página pública.',
    includedBadge: 'Incluido en todos los planes',
    includedBody:
      'Base de conocimiento, transcripción de llamadas a 1,5 tokens/min, roles base, conexión CRM y gabinete seguro.',
    currentPlan: 'Plan actual',
    notSelected: 'No seleccionado',
    includedTokens: 'Tokens incluidos',
    availableTokens: 'Tokens disponibles',
    safeMode: 'Pagos vía T-Bank',
    stepServer: '1. Elige servidor',
    stepServerBody: 'Configuración base: tokens IA, usuarios y frecuencia de actualización.',
    largeTeamHint:
      'amoCRM limita integraciones a 7 requests por segundo. Para equipos desde 30 managers recomendamos Enterprise Server + cola prioritaria.',
    stepModules: '2. Añade módulos IA',
    stepModulesBody: 'Capacidades conectables para el departamento de ventas.',
    stepTokens: '3. Tokens adicionales',
    stepTokensBody: 'Los tokens se gastan en llamadas, chats, emails, actualizaciones y tareas IA.',
    tokenBillingHint: 'Los cargos van por cada acción IA y análisis de llamadas. Tarifas abajo.',
    stepUsage: 'Tokens por acción',
    stepUsageBody: 'Tarificación transparente: las acciones IA tienen precio fijo.',
    stepSla: '4. SLA e infraestructura',
    stepSlaBody: 'Garantías adicionales, recursos dedicados y entorno privado.',
    summaryTitle: 'Tu tarifa',
    month: '1 mes',
    six: '6 meses −10%',
    year: '12 meses −20%',
    total: 'Total',
    perMonth: '/ mes',
    selected: 'Seleccionado',
    choosePlan: 'Elegir',
    collectPlan: 'Configurar tarifa',
    requestQuote: 'Pedir cálculo',
    disabledTitle: 'Pagos desactivados',
    disabledBody: 'Es una etapa UI segura. Compra real y cargos se activarán con un GO separado.',
    noAddons: 'Sin módulos IA',
    noTokens: 'Sin tokens extra',
    noSla: 'Sin SLA',
    byContract: 'por contrato',
    economy: 'ahorro',
    payForPeriod: 'a pagar por periodo',
    tokensIncluded: 'Tokens IA incluidos',
    users: 'Usuarios IA',
    update: 'Actualización',
    allTariffs: 'Base de conocimiento y transcripción básica incluidas en todos los planes.',
    aiUsers: 'usuarios IA',
    callMinutes: 'min/mes llamadas',
    usageGroups: [
      { title: 'Llamadas', rows: [['Transcripción', '1,5 tokens / min'], ['Análisis de llamada', '5 tokens'], ['Reporte de voz', '10 tokens']] },
      { title: 'Comunicaciones', rows: [['Respuesta en chat', '2 tokens'], ['Email IA / autorespuesta', '3 tokens'], ['Respuesta compleja por base de conocimiento', '5 tokens']] },
      { title: 'Autoacciones', rows: [['Crear tarea', '1 token'], ['Recordatorio', '1 token'], ['Mover deal en embudo', '1 token'], ['Generar factura', '2 tokens']] },
      { title: 'AI Head of Sales', rows: [['Análisis de deal', '5 tokens'], ['Historia completa del cliente', '20–30 tokens'], ['Escaneo diario por manager', '5 tokens']] },
    ],
    formulaTitle: 'Cómo se calcula el volumen',
    formulaBody:
      '1 token AIC9 equivale aproximadamente a 1.000 tokens LLM de procesamiento. Cuantos más emails, chats y transcripciones lee la IA, mayor el cargo.',
    formulaRows: [['Transcripciones', '5 × ~2.000', '~10.000'], ['Chats cliente', '30 × ~200', '~6.000'], ['Emails', '10 × ~500', '~5.000'], ['Prompt IA + reporte', '~4.000', '~4.000']],
  },
};

const MODULES: Record<'ru' | 'en' | 'es', Array<AddonItem<ModuleKey>>> = {
  ru: [
    { key: 'knowledge_bot', name: 'Чат-боты на базе знаний', description: 'Автоответы клиентам в чатах и письмах на основе базы знаний компании.', price: 5000, defaultActive: true },
    { key: 'ai_rop', name: 'РОП — контроль упущенных сделок', description: 'AI находит упущенные сделки, ставит задачи менеджерам и контролирует отдел.', price: 5000, defaultActive: true },
    { key: 'auto_actions', name: 'Автодействия системы', description: 'Счета, задачи на перезвон, перевод сделок и напоминания.', price: 3000 },
    { key: 'speech_analytics', name: 'Речевая аналитика', description: 'Эмоции, скрипты, ключевые моменты и причины отказов.', price: 7000 },
  ],
  en: [
    { key: 'knowledge_bot', name: 'Knowledge-base chatbots', description: 'Auto-replies in chats and emails using company knowledge base.', price: 5000, defaultActive: true },
    { key: 'ai_rop', name: 'AI Head of Sales control', description: 'AI finds missed deals, creates tasks and controls the sales team.', price: 5000, defaultActive: true },
    { key: 'auto_actions', name: 'System auto-actions', description: 'Invoices, callback tasks, deal movement and reminders.', price: 3000 },
    { key: 'speech_analytics', name: 'Speech analytics', description: 'Emotions, scripts, key moments and loss reasons.', price: 7000 },
  ],
  es: [
    { key: 'knowledge_bot', name: 'Chatbots con base de conocimiento', description: 'Auto-respuestas en chats y emails según la base de conocimiento.', price: 5000, defaultActive: true },
    { key: 'ai_rop', name: 'Control AI del Head of Sales', description: 'La IA encuentra deals perdidos, crea tareas y controla el equipo.', price: 5000, defaultActive: true },
    { key: 'auto_actions', name: 'Autoacciones del sistema', description: 'Facturas, tareas de llamada, mover deals y recordatorios.', price: 3000 },
    { key: 'speech_analytics', name: 'Analítica de voz', description: 'Emociones, scripts, puntos clave y razones de pérdida.', price: 7000 },
  ],
};

const TOKEN_PACKS: Record<'ru' | 'en' | 'es', Array<AddonItem<TokenPackKey> & { tokens: number }>> = {
  ru: [
    { key: 'none', name: 'Без пакета', description: 'Используем токены, включённые в сервер.', price: 0, tokens: 0 },
    { key: 'tokens_10000', name: '+10 000 токенов', description: 'Для дополнительных AI-задач и писем.', price: 3000, tokens: 10000 },
    { key: 'tokens_25000', name: '+25 000 токенов', description: 'Для активных звонков, писем и AI-РОПа.', price: 7000, tokens: 25000 },
    { key: 'tokens_50000', name: '+50 000 токенов', description: 'Для большой базы и регулярного анализа.', price: 12000, tokens: 50000 },
    { key: 'tokens_100000', name: '+100 000 токенов', description: 'Индивидуальная цена для большого объёма.', price: 0, tokens: 100000, custom: true },
  ],
  en: [
    { key: 'none', name: 'No package', description: 'Use tokens included in the server plan.', price: 0, tokens: 0 },
    { key: 'tokens_10000', name: '+10,000 tokens', description: 'For extra AI tasks and emails.', price: 3000, tokens: 10000 },
    { key: 'tokens_25000', name: '+25,000 tokens', description: 'For active calls, emails and AI sales control.', price: 7000, tokens: 25000 },
    { key: 'tokens_50000', name: '+50,000 tokens', description: 'For a large base and regular analysis.', price: 12000, tokens: 50000 },
    { key: 'tokens_100000', name: '+100,000 tokens', description: 'Custom price for high volume.', price: 0, tokens: 100000, custom: true },
  ],
  es: [
    { key: 'none', name: 'Sin paquete', description: 'Usa tokens incluidos en el servidor.', price: 0, tokens: 0 },
    { key: 'tokens_10000', name: '+10.000 tokens', description: 'Para tareas IA y emails extra.', price: 3000, tokens: 10000 },
    { key: 'tokens_25000', name: '+25.000 tokens', description: 'Para llamadas, emails y AI Head of Sales.', price: 7000, tokens: 25000 },
    { key: 'tokens_50000', name: '+50.000 tokens', description: 'Para base grande y análisis regular.', price: 12000, tokens: 50000 },
    { key: 'tokens_100000', name: '+100.000 tokens', description: 'Precio individual para gran volumen.', price: 0, tokens: 100000, custom: true },
  ],
};

const SLA_OPTIONS: Record<'ru' | 'en' | 'es', Array<AddonItem<SlaKey>>> = {
  ru: [
    { key: 'priority_queue', name: 'Приоритетная очередь', description: 'Более быстрая обработка задач и приоритет в очереди.', price: 10000 },
    { key: 'sla', name: 'SLA', description: 'Гарантированная поддержка, контроль нагрузки и регламент реакции.', price: 20000 },
    { key: 'private_contour', name: 'Частный контур', description: 'Выделенная инфраструктура и отдельные правила безопасности.', price: 0, custom: true },
  ],
  en: [
    { key: 'priority_queue', name: 'Priority queue', description: 'Faster task processing and queue priority.', price: 10000 },
    { key: 'sla', name: 'SLA', description: 'Guaranteed support, load control and response policy.', price: 20000 },
    { key: 'private_contour', name: 'Private setup', description: 'Dedicated infrastructure and custom security rules.', price: 0, custom: true },
  ],
  es: [
    { key: 'priority_queue', name: 'Cola prioritaria', description: 'Procesamiento más rápido y prioridad en la cola.', price: 10000 },
    { key: 'sla', name: 'SLA', description: 'Soporte garantizado, control de carga y reglamento de respuesta.', price: 20000 },
    { key: 'private_contour', name: 'Entorno privado', description: 'Infraestructura dedicada y reglas de seguridad separadas.', price: 0, custom: true },
  ],
};

export default function SubscriptionsPage() {
  const tConnections = useTranslations('cabinet.connections');
  const locale = useLocale();
  const localeKey = getLocaleKey(locale);
  const copy = COPY[localeKey];
  const { user } = useUserAuth();
  const { toast } = useToast();
  const wsId = user?.workspaces?.[0]?.id ?? null;
  const [period, setPeriod] = useState<PricingPeriodKey>('monthly');
  const [serverKey, setServerKey] = useState('enterprise');
  const [activeModules, setActiveModules] = useState<Set<ModuleKey>>(
    () => new Set(MODULES.ru.filter((item) => item.defaultActive).map((item) => item.key)),
  );
  const [tokenPackKey, setTokenPackKey] = useState<TokenPackKey>('none');
  const [activeSla, setActiveSla] = useState<Set<SlaKey>>(() => new Set());
  const [account, setAccount] = useState<BillingAccount | null>(null);
  const [tokenAccount, setTokenAccount] = useState<TokenAccount | null>(null);
  const [loading, setLoading] = useState(Boolean(wsId));
  const [paymentLoading, setPaymentLoading] = useState<'card' | 'invoice' | null>(null);
  const [paymentResult, setPaymentResult] = useState<PaymentCreateResponse | null>(null);
  const pricingPlans = getPricingPlans(locale);
  const modules = MODULES[localeKey];
  const tokenPacks = TOKEN_PACKS[localeKey];
  const slaOptions = SLA_OPTIONS[localeKey];

  useEffect(() => {
    if (!wsId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get<BillingAccount>(`/workspaces/${wsId}/billing/account`),
      api.get<TokenAccount>(`/workspaces/${wsId}/billing/token-account`),
    ])
      .then(([billing, tokens]) => {
        if (cancelled) return;
        setAccount(billing);
        setTokenAccount(tokens);
      })
      .catch(() => {
        if (cancelled) return;
        setAccount(null);
        setTokenAccount(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [wsId]);

  const currentPlanKey = matchPlanKey(tokenAccount?.plan_key ?? account?.plan ?? '');
  const currentPlanName = getPlanDisplayName(tokenAccount?.plan_key ?? account?.plan ?? '', locale, copy.notSelected);
  const selectedServer = pricingPlans.find((plan) => plan.key === serverKey) ?? pricingPlans[0];
  const selectedTokenPack = tokenPacks.find((item) => item.key === tokenPackKey) ?? tokenPacks[0];
  const selectedModules = modules.filter((item) => activeModules.has(item.key));
  const selectedSla = slaOptions.filter((item) => activeSla.has(item.key));
  const calc = useMemo(
    () =>
      calculatePlanTotal({
        server: selectedServer,
        modules: selectedModules,
        tokenPack: selectedTokenPack,
        sla: selectedSla,
        period,
      }),
    [period, selectedModules, selectedServer, selectedSla, selectedTokenPack],
  );

  if (!wsId) {
    return <EmptyState title={tConnections('noWorkspaceTitle')} description={tConnections('noWorkspaceBody')} />;
  }

  const paymentPayload = () => ({
    purchase_type: 'subscription',
    plan_key: selectedServer.key,
    period,
    token_pack_key: selectedTokenPack.key === 'none' ? undefined : selectedTokenPack.key,
    addon_keys: Array.from(activeModules),
    sla_keys: Array.from(activeSla).filter((key) => key !== 'private_contour'),
  });
  const hasCustomOption = selectedTokenPack.custom || selectedSla.some((item) => item.custom);
  const payByCard = async () => {
    if (!wsId) return;
    if (hasCustomOption) {
      toast({ kind: 'info', title: copy.requestQuote, description: copy.byContract });
      return;
    }
    setPaymentLoading('card');
    setPaymentResult(null);
    try {
      const data = await api.post<PaymentCreateResponse>(`/workspaces/${wsId}/billing/payments/card`, paymentPayload());
      setPaymentResult(data);
      if (data.payment_url) {
        window.location.assign(data.payment_url);
        return;
      }
      toast({ kind: 'success', title: 'Платёж создан', description: 'Ссылка на оплату сформирована.' });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : copy.disabledBody;
      toast({ kind: 'error', title: 'Оплата тарифа', description: message });
    } finally {
      setPaymentLoading(null);
    }
  };
  const requestInvoice = async () => {
    toast({
      kind: 'info',
      title: 'Счёт на юрлицо',
      description: 'Счёт с выбором компании делается на странице Баланс. Там доступен поиск по ИНН через DaData.',
    });
  };

  return (
    <div className="space-y-6">
      <header className="cabinet-page-hero rounded-2xl border border-border p-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <Badge tone="neutral">{copy.safeMode}</Badge>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-foreground">{copy.constructorTitle}</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.constructorBody}</p>
          </div>
          <div className="grid gap-3 text-sm sm:grid-cols-3 xl:min-w-[520px]">
            <SummaryPill label={copy.currentPlan} value={currentPlanName} />
            <SummaryPill label={copy.includedTokens} value={tokenAccount ? formatNumber(tokenAccount.included_monthly_tokens, locale) : '—'} />
            <SummaryPill label={copy.availableTokens} value={tokenAccount ? formatNumber(tokenAccount.available_tokens, locale) : '—'} />
          </div>
        </div>
        <div className="mt-5 rounded-xl border border-primary/20 bg-white/75 p-4 text-sm shadow-soft">
          <div className="flex items-center gap-2 font-semibold text-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            {copy.includedBadge}
          </div>
          <p className="mt-1 text-muted-foreground">{copy.includedBody}</p>
        </div>
      </header>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <main className="space-y-6">
            <BuilderSection
              icon={<DatabaseZap className="h-5 w-5 text-primary" />}
              title={copy.stepServer}
              body={copy.stepServerBody}
            >
              <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-4">
                {pricingPlans.map((plan) => {
                  const isSelected = plan.key === serverKey;
                  const isCurrent = plan.key === currentPlanKey;
                  return (
                    <button
                      key={plan.key}
                      type="button"
                      onClick={() => setServerKey(plan.key)}
                      className={cn(
                        'cabinet-pricing-card rounded-xl p-4 text-left transition hover:border-primary hover:shadow-soft',
                        plan.popular && 'is-popular border-primary/40',
                        isSelected && 'ring-2 ring-primary/35',
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h3 className="font-semibold">{serverDisplayName(plan)}</h3>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            <Badge tone={plan.popular ? 'info' : 'neutral'}>{plan.badge}</Badge>
                            {isCurrent ? <Badge tone="success">{copy.currentPlan}</Badge> : null}
                          </div>
                        </div>
                        {isSelected ? <Check className="h-5 w-5 text-primary" /> : null}
                      </div>
                      <div className="mt-4 text-2xl font-semibold tabular-nums">
                        {formatRub(plan.prices.monthly, locale)}
                      </div>
                      <div className="text-xs text-muted-foreground">{copy.perMonth}</div>
                      <p className="mt-3 min-h-12 text-sm text-muted-foreground">{plan.summary}</p>
                      <div className="mt-4 grid gap-2 text-sm">
                        <MiniMetric label="AI" value={`${formatNumber(plan.tokens, locale)} tokens`} />
                        <MiniMetric label={copy.aiUsers} value={formatNumber(plan.users, locale)} />
                        <MiniMetric label={copy.update} value={plan.updateInterval} />
                        <MiniMetric label={copy.callMinutes} value={formatNumber(plan.callMinutes, locale)} />
                      </div>
                    </button>
                  );
                })}
              </div>
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                {copy.largeTeamHint}
              </div>
            </BuilderSection>

            <BuilderSection
              icon={<MessageSquareText className="h-5 w-5 text-primary" />}
              title={copy.stepModules}
              body={copy.stepModulesBody}
            >
              <div className="grid gap-3 lg:grid-cols-2">
                {modules.map((item) => (
                  <AddonToggle
                    key={item.key}
                    item={item}
                    active={activeModules.has(item.key)}
                    locale={locale}
                    byContract={copy.byContract}
                    onToggle={() => setActiveModules(toggleSet(activeModules, item.key))}
                  />
                ))}
              </div>
            </BuilderSection>

            <BuilderSection
              icon={<WalletCards className="h-5 w-5 text-primary" />}
              title={copy.stepTokens}
              body={copy.stepTokensBody}
            >
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                {tokenPacks.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setTokenPackKey(item.key)}
                    className={cn(
                      'rounded-xl border p-4 text-left transition hover:border-primary hover:bg-primary/5',
                      tokenPackKey === item.key ? 'border-primary bg-primary/10' : 'border-border bg-white',
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-semibold text-foreground">{item.name}</div>
                      {tokenPackKey === item.key ? <Check className="h-4 w-4 text-primary" /> : null}
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">{item.description}</p>
                    <div className="mt-3 text-sm font-semibold text-foreground">
                      {item.custom ? copy.byContract : item.price > 0 ? `+${formatRub(item.price, locale)} ${copy.perMonth}` : formatRub(0, locale)}
                    </div>
                  </button>
                ))}
              </div>
              <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 p-4 text-sm text-muted-foreground">
                <strong className="text-foreground">{copy.tokenBillingHint}</strong>
              </div>
            </BuilderSection>

            <BuilderSection
              icon={<ReceiptText className="h-5 w-5 text-primary" />}
              title={copy.stepUsage}
              body={copy.stepUsageBody}
            >
              <div className="grid gap-3 lg:grid-cols-2">
                {copy.usageGroups.map((group) => (
                  <div key={group.title} className="rounded-xl border border-border bg-white p-4">
                    <h3 className="font-semibold text-foreground">{group.title}</h3>
                    <div className="mt-3 space-y-2">
                      {group.rows.map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between gap-3 text-sm">
                          <span className="text-muted-foreground">{label}</span>
                          <strong className="text-right text-foreground">{value}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 rounded-xl border border-border bg-muted/40 p-4">
                <h3 className="font-semibold text-foreground">{copy.formulaTitle}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{copy.formulaBody}</p>
                <div className="mt-4 grid gap-2">
                  {copy.formulaRows.map(([label, calcRow, result]) => (
                    <div key={label} className="grid grid-cols-[1fr_auto_auto] gap-3 rounded-lg bg-white px-3 py-2 text-sm">
                      <span className="text-muted-foreground">{label}</span>
                      <span className="text-muted-foreground">{calcRow}</span>
                      <strong>{result}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </BuilderSection>

            <BuilderSection
              icon={<ShieldCheck className="h-5 w-5 text-primary" />}
              title={copy.stepSla}
              body={copy.stepSlaBody}
            >
              <div className="grid gap-3 lg:grid-cols-3">
                {slaOptions.map((item) => (
                  <AddonToggle
                    key={item.key}
                    item={item}
                    active={activeSla.has(item.key)}
                    locale={locale}
                    byContract={copy.byContract}
                    onToggle={() => setActiveSla(toggleSet(activeSla, item.key))}
                  />
                ))}
              </div>
            </BuilderSection>
          </main>

          <aside className="xl:sticky xl:top-6 xl:self-start">
            <section className="cabinet-page-hero rounded-2xl border border-border p-5 shadow-soft">
              <h2 className="text-xl font-semibold">{copy.summaryTitle}</h2>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {[
                  ['monthly', copy.month],
                  ['six', copy.six],
                  ['year', copy.year],
                ].map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setPeriod(key as PricingPeriodKey)}
                    className={cn(
                      'rounded-lg border px-2 py-2 text-xs font-medium transition',
                      period === key ? 'border-primary bg-primary text-white' : 'border-border bg-white text-foreground hover:bg-muted',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="mt-5 space-y-3">
                <SummaryLine name={serverDisplayName(selectedServer)} value={formatRub(selectedServer.prices.monthly, locale)} />
                {selectedModules.length > 0 ? (
                  selectedModules.map((item) => (
                    <SummaryLine key={item.key} name={item.name} value={`+${formatRub(item.price, locale)}`} />
                  ))
                ) : (
                  <SummaryLine muted name={copy.noAddons} value="—" />
                )}
                {selectedTokenPack.key !== 'none' ? (
                  <SummaryLine
                    name={selectedTokenPack.name}
                    value={selectedTokenPack.custom ? copy.byContract : `+${formatRub(selectedTokenPack.price, locale)}`}
                  />
                ) : (
                  <SummaryLine muted name={copy.noTokens} value="—" />
                )}
                {selectedSla.length > 0 ? (
                  selectedSla.map((item) => (
                    <SummaryLine
                      key={item.key}
                      name={item.name}
                      value={item.custom ? copy.byContract : `+${formatRub(item.price, locale)}`}
                    />
                  ))
                ) : (
                  <SummaryLine muted name={copy.noSla} value="—" />
                )}
              </div>

              <div className="my-5 h-px bg-border" />
              <div className="flex items-end justify-between gap-3">
                <div className="text-sm text-muted-foreground">{copy.total}</div>
                <div className="text-right">
                  <div className="text-3xl font-semibold tabular-nums">{formatRub(calc.monthlyAfterDiscount, locale)}</div>
                  <div className="text-xs text-muted-foreground">{copy.perMonth}</div>
                </div>
              </div>
              {period !== 'monthly' ? (
                <div className="mt-3 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">
                  <div>
                    {copy.payForPeriod}: <strong>{formatRub(calc.totalForPeriod, locale)}</strong>
                  </div>
                  <div>
                    {copy.economy}: <strong>{formatRub(calc.saved, locale)}</strong>
                  </div>
                </div>
              ) : null}

              <div className="mt-4 rounded-xl border border-border bg-white p-4 text-sm">
                <SummaryMeta label={copy.tokensIncluded} value={formatNumber(selectedServer.tokens + selectedTokenPack.tokens, locale)} />
                <SummaryMeta label={copy.users} value={formatNumber(selectedServer.users, locale)} />
                <SummaryMeta label={copy.update} value={selectedServer.updateInterval} />
              </div>

              <div className="mt-5 grid gap-2">
                <Button type="button" onClick={payByCard} loading={paymentLoading === 'card'} disabled={hasCustomOption}>
                  <CreditCard className="h-4 w-4" />
                  Оплатить картой
                </Button>
                <Button type="button" variant="secondary" onClick={requestInvoice} loading={paymentLoading === 'invoice'}>
                  <FileText className="h-4 w-4" />
                  Счёт на юрлицо
                </Button>
              </div>
              {paymentResult ? (
                <div className="mt-4 rounded-lg border border-border bg-muted/40 p-3 text-sm">
                  <div className="font-medium">Заказ {paymentResult.order.id}</div>
                  <div className="text-muted-foreground">
                    Статус: {paymentResult.order.status} · сумма: {formatRub(paymentResult.order.amount_cents / 100, locale)}
                  </div>
                </div>
              ) : null}
              <p className="mt-4 text-xs leading-5 text-muted-foreground">{copy.allTariffs}</p>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}

function BuilderSection({
  icon,
  title,
  body,
  children,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  children: ReactNode;
}) {
  return (
    <section className="cabinet-page-hero rounded-2xl border border-border p-5">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">{icon}</div>
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{body}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function AddonToggle({
  item,
  active,
  locale,
  byContract,
  onToggle,
}: {
  item: AddonItem;
  active: boolean;
  locale: string;
  byContract: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        'flex min-h-32 items-start justify-between gap-4 rounded-xl border p-4 text-left transition hover:border-primary hover:bg-primary/5',
        active ? 'border-primary bg-primary/10' : 'border-border bg-white',
      )}
    >
      <div>
        <div className="font-semibold text-foreground">
          {item.name}
          {item.custom ? <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{byContract}</span> : null}
        </div>
        <p className="mt-2 text-sm leading-5 text-muted-foreground">{item.description}</p>
        <div className="mt-3 text-sm font-semibold text-foreground">
          {item.custom ? byContract : `+${formatRub(item.price, locale)} / ${locale === 'en' ? 'mo' : locale === 'es' ? 'mes' : 'мес'}`}
        </div>
      </div>
      <span
        className={cn(
          'mt-1 flex h-6 w-11 shrink-0 items-center rounded-full border p-0.5 transition',
          active ? 'border-primary bg-primary' : 'border-border bg-muted',
        )}
      >
        <span className={cn('h-4 w-4 rounded-full bg-white shadow transition', active && 'translate-x-5')} />
      </span>
    </button>
  );
}

function SummaryPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-white/80 px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-semibold text-foreground">{value}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/40 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function SummaryLine({ name, value, muted = false }: { name: string; value: string; muted?: boolean }) {
  return (
    <div className={cn('flex items-center justify-between gap-4 text-sm', muted && 'text-muted-foreground')}>
      <span className="min-w-0 truncate">{name}</span>
      <span className="shrink-0 font-semibold">{value}</span>
    </div>
  );
}

function SummaryMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-muted-foreground">{label}</span>
      <strong className="text-right">{value}</strong>
    </div>
  );
}

function formatRub(value: number, locale: string): string {
  return new Intl.NumberFormat(toIntlLocale(locale), {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value);
}

function matchPlanKey(plan: string): string | null {
  const normalized = plan.toLowerCase();
  return getPricingPlans('ru').find((item) => normalized.includes(item.key) || normalized.includes(item.name.toLowerCase()))?.key ?? null;
}

function getPlanDisplayName(plan: string, locale: string, fallback: string): string {
  const normalized = plan.toLowerCase();
  if (!normalized || normalized === 'free' || normalized === 'paygo') return fallback;
  return (
    getPricingPlans(locale).find((item) => {
      const name = item.name.toLowerCase();
      return normalized.includes(item.key) || normalized.includes(name);
    })?.name ?? plan
  );
}

function getLocaleKey(locale: string): 'ru' | 'en' | 'es' {
  if (locale === 'en') return 'en';
  if (locale === 'es') return 'es';
  return 'ru';
}

function serverDisplayName(plan: PricingPlan): string {
  if (plan.key === 'enterprise') return 'Enterprise Server';
  return `Server ${plan.name}`;
}

function toggleSet<T>(source: Set<T>, key: T): Set<T> {
  const next = new Set(source);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

function calculatePlanTotal({
  server,
  modules,
  tokenPack,
  sla,
  period,
}: {
  server: PricingPlan;
  modules: AddonItem[];
  tokenPack: AddonItem<TokenPackKey>;
  sla: AddonItem[];
  period: PricingPeriodKey;
}) {
  const moduleTotal = modules.reduce((sum, item) => sum + (item.custom ? 0 : item.price), 0);
  const tokenTotal = tokenPack.custom ? 0 : tokenPack.price;
  const slaTotal = sla.reduce((sum, item) => sum + (item.custom ? 0 : item.price), 0);
  const monthlyBeforeDiscount = server.prices.monthly + moduleTotal + tokenTotal + slaTotal;
  const months = period === 'year' ? 12 : period === 'six' ? 6 : 1;
  const discount = period === 'year' ? 0.2 : period === 'six' ? 0.1 : 0;
  const monthlyAfterDiscount = Math.round(monthlyBeforeDiscount * (1 - discount));
  const totalForPeriod = monthlyAfterDiscount * months;
  const saved = monthlyBeforeDiscount * months - totalForPeriod;
  return { monthlyBeforeDiscount, monthlyAfterDiscount, totalForPeriod, saved };
}
