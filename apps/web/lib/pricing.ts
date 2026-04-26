export type PricingPeriodKey = 'monthly' | 'six' | 'year';

export interface PricingPlan {
  key: string;
  name: string;
  badge: string;
  summary: string;
  prices: Record<PricingPeriodKey, number>;
  tokens: number;
  users: number;
  callMinutes: number;
  updateInterval: string;
  rollover: string;
  topup: string;
  features: string[];
  excluded: string[];
  popular?: boolean;
  customPriceLabel?: string;
  customPeriodLabel?: string;
}

export const billingPeriods: Array<{
  key: PricingPeriodKey;
  label: string;
  suffix: string;
}> = [
  { key: 'monthly', label: 'Помесячно', suffix: '/мес' },
  { key: 'six', label: '6 месяцев · −10%', suffix: 'за 6 мес.' },
  { key: 'year', label: 'Год · −20%', suffix: 'за год' },
];

export const pricingPlans: PricingPlan[] = [
  {
    key: 'start',
    name: 'Старт',
    badge: 'Только звонки',
    summary: 'Для маленькой команды, которой нужен контроль звонков и базовая аналитика.',
    prices: { monthly: 4990, six: 26900, year: 47900 },
    tokens: 3000,
    users: 3,
    callMinutes: 2000,
    updateInterval: '1 раз в день',
    rollover: 'до 1 месяца',
    topup: 'Call Pack',
    features: [
      'AI-анализ звонков и саммари разговора',
      'Результат звонка, теги, возражения и next step',
      'Карточка клиента и история коммуникаций',
      'Базовые дашборды',
      'Viewer-доступы без ограничений',
    ],
    excluded: ['AI-чат и анализ писем не входят', 'Автозадачи и AI-черновики не входят'],
  },
  {
    key: 'team',
    name: 'Команда',
    badge: 'Звонки + чат + письма',
    summary: 'Для отдела продаж, который работает со звонками, письмами и историей клиента.',
    prices: { monthly: 9990, six: 53900, year: 95900 },
    tokens: 9000,
    users: 10,
    callMinutes: 6000,
    updateInterval: 'каждые 10 часов',
    rollover: 'до 2 месяцев',
    topup: 'Universal Pack',
    features: [
      'Всё из тарифа Старт',
      'AI-чат по клиенту, сделке и истории общения',
      'Анализ текста писем и черновик ответа',
      'Сводное саммари по всей истории клиента',
      'Командные дашборды и единая база клиентов',
      'Viewer-доступы без ограничений',
    ],
    excluded: ['Автозадачи и AI-черновики сообщений не входят'],
  },
  {
    key: 'pro',
    name: 'Про',
    badge: 'AI-операционка ОП',
    summary: 'Для активного отдела продаж, где AI анализирует, помогает действовать и обновляет базу.',
    prices: { monthly: 14990, six: 80900, year: 143900 },
    tokens: 18000,
    users: 20,
    callMinutes: 12000,
    updateInterval: 'каждый час',
    rollover: 'до 3 месяцев',
    topup: 'Universal Pack',
    popular: true,
    features: [
      'Всё из тарифа Команда',
      'Автозадачи менеджерам по итогам звонков и писем',
      'AI-черновики follow-up, WhatsApp, e-mail и сообщений',
      'Автообновление базы знаний и карточки клиента',
      'Управленческие дашборды и сигналы для РОПа',
      'Приоритетная обработка и полная история коммуникаций',
      'Viewer-доступы без ограничений',
    ],
    excluded: [],
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    badge: 'SLA + частный контур',
    summary: 'Для больших отделов продаж, где нужны крупные лимиты, частые обновления, SLA и кастомные правила анализа.',
    prices: { monthly: 39990, six: 215900, year: 383900 },
    tokens: 50000,
    users: 50,
    callMinutes: 30000,
    updateInterval: 'каждые 15 минут',
    rollover: 'до 6 месяцев',
    topup: 'Enterprise Pack',
    features: [
      'Всё из тарифа Про',
      'Индивидуальные лимиты пользователей, токенов и обновлений',
      'SLA, приоритетная очередь и контроль нагрузки amoCRM',
      'Частный контур или выделенная инфраструктура по договору',
      'Кастомные правила аналитики, отчётов и уведомлений',
      'Расширенная поддержка и сопровождение запуска',
    ],
    excluded: [],
  },
];

export const aiTokenRates = [
  {
    value: '1.5',
    title: '1 минута AI-анализа звонка',
    body: 'Транскрипт, саммари, outcome, теги, next step, возражения и обновление карточки клиента.',
  },
  {
    value: '0.5',
    title: 'AI-чат',
    body: 'Вопросы по клиенту, сделке, истории общения, звонкам, письмам и контексту менеджера.',
  },
  {
    value: '0.5',
    title: 'Анализ текста письма',
    body: 'Саммари письма, намерение клиента, риск, важность, следующий шаг и черновик ответа.',
  },
  {
    value: '0.5',
    title: 'Автозадача или AI-черновик',
    body: 'Постановка задачи менеджеру, follow-up, WhatsApp/e-mail черновик или внутреннее уведомление.',
  },
];

export const topUpPacks = [
  {
    key: 'call3000',
    name: 'Call Pack 3 000',
    scope: 'Только для тарифа Старт. Используется только на AI-анализ звонков.',
    tags: ['до 2 000 минут', 'для Start'],
    prices: { monthly: 2990, six: 2990, year: 2990 },
  },
  {
    key: 'u3000',
    name: 'Universal 3 000',
    scope: 'Для тарифов Команда, Про и Enterprise. Подходит для любых AI-действий.',
    tags: ['универсальный', 'Team / Pro / Enterprise'],
    prices: { monthly: 2990, six: 2990, year: 2990 },
  },
  {
    key: 'u10000',
    name: 'Universal 10 000',
    scope: 'Для активных команд с большим количеством звонков, чатов и анализа переписки.',
    tags: ['до 6 666 минут', 'выгоднее по объёму'],
    prices: { monthly: 8490, six: 7990, year: 7490 },
  },
  {
    key: 'u25000',
    name: 'Universal 25 000',
    scope: 'Для больших отделов продаж и компаний, где AI активно участвует в процессе.',
    tags: ['крупные объёмы', 'лучшая цена'],
    prices: { monthly: 19990, six: 18990, year: 17990 },
  },
];

export const launchServices = [
  {
    name: 'Быстрый запуск',
    price: '29 900 ₽',
    body: 'Подключение аккаунта, один канал, базовые дашборды, роли, проверка токенов и одно обучение команды.',
  },
  {
    name: 'Бизнес-внедрение',
    price: '69 900–99 900 ₽',
    body: 'Экспресс-аудит, 2–3 интеграции, звонки + письма, автозадачи, 3–5 дашбордов и обучение.',
  },
  {
    name: 'Полный аудит',
    price: '79 900–129 900 ₽',
    body: 'Анализ CRM, звонков, писем, процессов, потерь, качества базы и roadmap внедрения AI.',
  },
  {
    name: 'Под ключ',
    price: '129 900–199 900 ₽',
    body: 'Полный аудит, настройка, интеграции, дашборды, правила AI-анализа, обучение и сопровождение запуска.',
  },
];

type LocaleLike = string | undefined;
type PlanPatch = Pick<
  PricingPlan,
  | 'name'
  | 'badge'
  | 'summary'
  | 'updateInterval'
  | 'rollover'
  | 'topup'
  | 'features'
  | 'excluded'
  | 'customPriceLabel'
  | 'customPeriodLabel'
>;
type TopUpPatch = Pick<(typeof topUpPacks)[number], 'name' | 'scope' | 'tags'>;
type LaunchPatch = Pick<(typeof launchServices)[number], 'name' | 'price' | 'body'>;

const localizedBillingPeriods: Record<string, typeof billingPeriods> = {
  en: [
    { key: 'monthly', label: 'Monthly', suffix: '/mo' },
    { key: 'six', label: '6 months · −10%', suffix: 'for 6 mo.' },
    { key: 'year', label: 'Year · −20%', suffix: 'for year' },
  ],
  es: [
    { key: 'monthly', label: 'Mensual', suffix: '/mes' },
    { key: 'six', label: '6 meses · −10%', suffix: 'por 6 meses' },
    { key: 'year', label: 'Año · −20%', suffix: 'por año' },
  ],
};

const localizedPlans: Record<string, Record<string, PlanPatch>> = {
  en: {
    start: {
      name: 'Start',
      badge: 'Calls only',
      summary: 'For a small team that needs call control and basic analytics.',
      updateInterval: 'once a day',
      rollover: 'up to 1 month',
      topup: 'Call Pack',
      features: [
        'AI call analysis and conversation summary',
        'Call outcome, tags, objections and next step',
        'Client card and communication history',
        'Basic dashboards',
        'Unlimited viewer access',
      ],
      excluded: ['AI chat and email analysis are not included', 'Auto-tasks and AI drafts are not included'],
    },
    team: {
      name: 'Team',
      badge: 'Calls + chat + email',
      summary: 'For a sales team that works with calls, emails and client history.',
      updateInterval: 'every 10 hours',
      rollover: 'up to 2 months',
      topup: 'Universal Pack',
      features: [
        'Everything in Start',
        'AI chat by client, deal and communication history',
        'Email text analysis and reply draft',
        'Unified summary for the whole client history',
        'Team dashboards and unified client base',
        'Unlimited viewer access',
      ],
      excluded: ['Auto-tasks and AI message drafts are not included'],
    },
    pro: {
      name: 'Pro',
      badge: 'AI sales operations',
      summary: 'For an active sales department where AI analyzes, assists and updates the base.',
      updateInterval: 'hourly',
      rollover: 'up to 3 months',
      topup: 'Universal Pack',
      features: [
        'Everything in Team',
        'Auto-tasks for managers based on calls and emails',
        'AI follow-up, WhatsApp, email and message drafts',
        'Automatic knowledge base and client card updates',
        'Management dashboards and Head of Sales signals',
        'Priority processing and full communication history',
        'Unlimited viewer access',
      ],
      excluded: [],
    },
    enterprise: {
      name: 'Enterprise',
      badge: 'SLA + private setup',
      summary: 'For large sales teams that need high limits, frequent updates, SLA and custom analysis rules.',
      updateInterval: 'every 15 minutes',
      rollover: 'up to 6 months',
      topup: 'Enterprise Pack',
      features: [
        'Everything in Pro',
        'Custom user, token and update limits',
        'SLA, priority queue and amoCRM load control',
        'Private setup or dedicated infrastructure by contract',
        'Custom analytics, reports and notification rules',
        'Extended support and launch assistance',
      ],
      excluded: [],
    },
  },
  es: {
    start: {
      name: 'Inicio',
      badge: 'Solo llamadas',
      summary: 'Para un equipo pequeño que necesita control de llamadas y analítica básica.',
      updateInterval: '1 vez al día',
      rollover: 'hasta 1 mes',
      topup: 'Call Pack',
      features: [
        'Análisis IA de llamadas y resumen de conversación',
        'Resultado de llamada, etiquetas, objeciones y siguiente paso',
        'Ficha del cliente e historial de comunicaciones',
        'Dashboards básicos',
        'Accesos viewer sin límites',
      ],
      excluded: ['AI chat y análisis de emails no incluidos', 'Auto-tareas y borradores IA no incluidos'],
    },
    team: {
      name: 'Equipo',
      badge: 'Llamadas + chat + emails',
      summary: 'Para un equipo de ventas que trabaja con llamadas, emails e historial del cliente.',
      updateInterval: 'cada 10 horas',
      rollover: 'hasta 2 meses',
      topup: 'Universal Pack',
      features: [
        'Todo lo del plan Inicio',
        'AI chat por cliente, deal e historial de comunicación',
        'Análisis de emails y borrador de respuesta',
        'Resumen unificado de todo el historial del cliente',
        'Dashboards de equipo y base única de clientes',
        'Accesos viewer sin límites',
      ],
      excluded: ['Auto-tareas y borradores IA de mensajes no incluidos'],
    },
    pro: {
      name: 'Pro',
      badge: 'Operaciones de ventas con IA',
      summary: 'Para un departamento de ventas activo donde la IA analiza, ayuda y actualiza la base.',
      updateInterval: 'cada hora',
      rollover: 'hasta 3 meses',
      topup: 'Universal Pack',
      features: [
        'Todo lo del plan Equipo',
        'Auto-tareas para managers según llamadas y emails',
        'Borradores IA de follow-up, WhatsApp, email y mensajes',
        'Actualización automática de base de conocimiento y ficha del cliente',
        'Dashboards de gestión y señales para el Head of Sales',
        'Procesamiento prioritario e historial completo de comunicaciones',
        'Accesos viewer sin límites',
      ],
      excluded: [],
    },
    enterprise: {
      name: 'Enterprise',
      badge: 'SLA + entorno privado',
      summary: 'Para grandes equipos de ventas que necesitan límites altos, actualizaciones frecuentes, SLA y reglas de análisis personalizadas.',
      updateInterval: 'cada 15 minutos',
      rollover: 'hasta 6 meses',
      topup: 'Enterprise Pack',
      features: [
        'Todo lo del plan Pro',
        'Límites personalizados de usuarios, tokens y actualizaciones',
        'SLA, cola prioritaria y control de carga de amoCRM',
        'Entorno privado o infraestructura dedicada por contrato',
        'Reglas personalizadas de analítica, reportes y notificaciones',
        'Soporte extendido y acompañamiento de lanzamiento',
      ],
      excluded: [],
    },
  },
};

const localizedAiRates: Record<string, typeof aiTokenRates> = {
  en: [
    {
      value: '1.5',
      title: '1 minute of AI call analysis',
      body: 'Transcript, summary, outcome, tags, next step, objections and client card update.',
    },
    {
      value: '0.5',
      title: 'AI chat',
      body: 'Questions about the client, deal, communication history, calls, emails and manager context.',
    },
    {
      value: '0.5',
      title: 'Email text analysis',
      body: 'Email summary, client intent, risk, priority, next step and reply draft.',
    },
    {
      value: '0.5',
      title: 'Auto-task or AI draft',
      body: 'Manager task, follow-up, WhatsApp/email draft or internal notification.',
    },
  ],
  es: [
    {
      value: '1.5',
      title: '1 minuto de análisis IA de llamada',
      body: 'Transcripción, resumen, outcome, etiquetas, siguiente paso, objeciones y actualización de ficha del cliente.',
    },
    {
      value: '0.5',
      title: 'AI chat',
      body: 'Preguntas sobre cliente, deal, historial de comunicación, llamadas, emails y contexto del manager.',
    },
    {
      value: '0.5',
      title: 'Análisis de texto de email',
      body: 'Resumen del email, intención del cliente, riesgo, prioridad, siguiente paso y borrador de respuesta.',
    },
    {
      value: '0.5',
      title: 'Auto-tarea o borrador IA',
      body: 'Tarea para manager, follow-up, borrador de WhatsApp/email o notificación interna.',
    },
  ],
};

const localizedTopUps: Record<string, Record<string, TopUpPatch>> = {
  en: {
    call3000: {
      name: 'Call Pack 3,000',
      scope: 'Only for Start plan. Used only for AI call analysis.',
      tags: ['up to 2,000 minutes', 'for Start'],
    },
    u3000: {
      name: 'Universal 3,000',
      scope: 'For Team, Pro and Enterprise plans. Works for any AI action.',
      tags: ['universal', 'Team / Pro / Enterprise'],
    },
    u10000: {
      name: 'Universal 10,000',
      scope: 'For active teams with many calls, chats and email analysis.',
      tags: ['up to 6,666 minutes', 'better by volume'],
    },
    u25000: {
      name: 'Universal 25,000',
      scope: 'For large sales departments and companies where AI is active in the process.',
      tags: ['large volumes', 'best price'],
    },
  },
  es: {
    call3000: {
      name: 'Call Pack 3.000',
      scope: 'Solo para el plan Inicio. Se usa únicamente para análisis IA de llamadas.',
      tags: ['hasta 2.000 minutos', 'para Inicio'],
    },
    u3000: {
      name: 'Universal 3.000',
      scope: 'Para planes Equipo, Pro y Enterprise. Sirve para cualquier acción IA.',
      tags: ['universal', 'Equipo / Pro / Enterprise'],
    },
    u10000: {
      name: 'Universal 10.000',
      scope: 'Para equipos activos con muchas llamadas, chats y análisis de emails.',
      tags: ['hasta 6.666 minutos', 'mejor por volumen'],
    },
    u25000: {
      name: 'Universal 25.000',
      scope: 'Para grandes departamentos de ventas y empresas donde la IA participa activamente.',
      tags: ['grandes volúmenes', 'mejor precio'],
    },
  },
};

const localizedLaunchServices: Record<string, LaunchPatch[]> = {
  en: [
    {
      name: 'Quick start',
      price: '29,900 ₽',
      body: 'Account connection, one channel, basic dashboards, roles, token check and one team training.',
    },
    {
      name: 'Business implementation',
      price: '69,900–99,900 ₽',
      body: 'Express audit, 2–3 integrations, calls + emails, auto-tasks, 3–5 dashboards and training.',
    },
    {
      name: 'Full audit',
      price: '79,900–129,900 ₽',
      body: 'CRM, calls, emails, processes, losses, database quality and AI implementation roadmap analysis.',
    },
    {
      name: 'Turnkey',
      price: '129,900–199,900 ₽',
      body: 'Full audit, setup, integrations, dashboards, AI analysis rules, training and launch support.',
    },
  ],
  es: [
    {
      name: 'Inicio rápido',
      price: '29.900 ₽',
      body: 'Conexión de cuenta, un canal, dashboards básicos, roles, revisión de tokens y una formación del equipo.',
    },
    {
      name: 'Implementación business',
      price: '69.900–99.900 ₽',
      body: 'Auditoría express, 2–3 integraciones, llamadas + emails, auto-tareas, 3–5 dashboards y formación.',
    },
    {
      name: 'Auditoría completa',
      price: '79.900–129.900 ₽',
      body: 'Análisis de CRM, llamadas, emails, procesos, pérdidas, calidad de base y roadmap de implementación IA.',
    },
    {
      name: 'Llave en mano',
      price: '129.900–199.900 ₽',
      body: 'Auditoría completa, configuración, integraciones, dashboards, reglas de análisis IA, formación y soporte de lanzamiento.',
    },
  ],
};

function normalizedLocale(locale: LocaleLike): 'ru' | 'en' | 'es' {
  if (locale?.startsWith('en')) return 'en';
  if (locale?.startsWith('es')) return 'es';
  return 'ru';
}

export function getBillingPeriods(locale?: LocaleLike): typeof billingPeriods {
  return localizedBillingPeriods[normalizedLocale(locale)] ?? billingPeriods;
}

export function getPricingPlans(locale?: LocaleLike): typeof pricingPlans {
  const patches = localizedPlans[normalizedLocale(locale)];
  if (!patches) return pricingPlans;
  return pricingPlans.map((plan) => ({ ...plan, ...(patches[plan.key] ?? {}) })) as typeof pricingPlans;
}

export function getAiTokenRates(locale?: LocaleLike): typeof aiTokenRates {
  return localizedAiRates[normalizedLocale(locale)] ?? aiTokenRates;
}

export function getTopUpPacks(locale?: LocaleLike): typeof topUpPacks {
  const patches = localizedTopUps[normalizedLocale(locale)];
  if (!patches) return topUpPacks;
  return topUpPacks.map((pack) => ({ ...pack, ...(patches[pack.key] ?? {}) })) as typeof topUpPacks;
}

export function getLaunchServices(locale?: LocaleLike): typeof launchServices {
  return localizedLaunchServices[normalizedLocale(locale)] ?? launchServices;
}
