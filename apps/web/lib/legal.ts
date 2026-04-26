import type { Locale } from '@/i18n/routing';

export type LegalDocumentKey = 'legal' | 'terms' | 'privacy' | 'personalData';

export type LegalDocument = {
  key: LegalDocumentKey;
  title: string;
  eyebrow: string;
  updatedAt: string;
  intro: string[];
  sections: Array<{
    title: string;
    body?: string[];
    bullets?: string[];
  }>;
  related?: Array<{
    title: string;
    description: string;
    href: string;
  }>;
  disclaimer?: string;
};

const legalEntityRu = [
  'Оператор и владелец сервиса: Индивидуальный предприниматель Сашнев Сергей Александрович.',
  'ИНН: 860229601650. ОГРНИП: 321861700018582.',
  'Юридический адрес: 628404, Россия, Ханты-Мансийский автономный округ - Югра АО, г. Сургут, ул. Энтузиастов, д. 8, кв. 83.',
];

const legalEntityBankRu = [
  'Банк: АО «ТБанк». Расчетный счет: 40802810900004504760.',
  'БИК банка: 044525974. Корреспондентский счет: 30101810145250000974.',
  'ИНН банка: 7710140679. Юридический адрес банка: 127287, г. Москва, ул. Хуторская 2-я, д. 38А, стр. 26.',
];

const legalEntityEn = [
  'Service operator and owner: Sole Proprietor Sashnev Sergey Aleksandrovich.',
  'Taxpayer ID / INN: 860229601650. State registration number / OGRNIP: 321861700018582.',
  'Legal address: Apt. 83, 8 Entuziastov St., Surgut, Khanty-Mansi Autonomous Okrug - Yugra, Russia, 628404.',
];

const legalEntityBankEn = [
  'Bank: JSC TBank. Settlement account: 40802810900004504760.',
  'Bank BIC: 044525974. Correspondent account: 30101810145250000974.',
  'Bank INN: 7710140679. Bank legal address: 38A, bldg. 26, 2nd Khutorskaya St., Moscow, 127287, Russia.',
];

const legalEntityEs = [
  'Operador y titular del servicio: Empresario individual Sashnev Sergey Aleksandrovich.',
  'INN: 860229601650. OGRNIP: 321861700018582.',
  'Dirección legal: apto. 83, calle Entuziastov 8, Surgut, Distrito Autónomo de Janty-Mansi - Yugra, Rusia, 628404.',
];

const legalEntityBankEs = [
  'Banco: JSC TBank. Cuenta corriente: 40802810900004504760.',
  'BIC del banco: 044525974. Cuenta corresponsal: 30101810145250000974.',
  'INN del banco: 7710140679. Dirección legal del banco: calle Khutorskaya 2-ya, 38A, edif. 26, Moscú, 127287, Rusia.',
];

const ruDocs: Record<LegalDocumentKey, LegalDocument> = {
  legal: {
    key: 'legal',
    title: 'Правовая информация CODE9 Analytics',
    eyebrow: 'Legal / privacy / terms',
    updatedAt: '24 апреля 2026',
    intro: [
      'Этот раздел объединяет основные документы для сайта, личного кабинета и сервиса аналитики CODE9 Analytics.',
      'Сервис помогает подключать amoCRM, выгружать данные в отдельный контур клиента, строить дашборды и готовить AI-анализ по выбранным данным.',
    ],
    related: [
      {
        title: 'Условия использования',
        description: 'Правила регистрации, работы с кабинетом, CRM-подключениями, токенами и аналитикой.',
        href: '/terms',
      },
      {
        title: 'Политика конфиденциальности',
        description: 'Какие данные обрабатываются, зачем они нужны и как защищаются.',
        href: '/privacy',
      },
      {
        title: 'Обработка персональных данных',
        description: 'Согласие и основные правила обработки персональных данных пользователей и клиентов.',
        href: '/personal-data',
      },
    ],
    sections: [
      {
        title: 'Владелец сервиса и контакты',
        body: [
          ...legalEntityRu,
          ...legalEntityBankRu,
          'Контакт для правовых, технических и privacy-запросов: support@aicode9.ru.',
        ],
      },
      {
        title: 'Что относится к сервису',
        bullets: [
          'публичный сайт и страницы входа в личный кабинет;',
          'личный кабинет клиента и кабинет администратора;',
          'подключение amoCRM и хранение технической информации о подключении;',
          'выгрузки CRM-данных, дашборды, отчеты и расчет AIC9-токенов;',
          'уведомления, журналы операций и будущие AI-функции.',
        ],
      },
      {
        title: 'Важные ограничения',
        body: [
          'Реальные платежи, AI-обработка, хранение токенов интеграций и support-доступ включаются только в тех режимах, которые явно активированы в продукте и описаны в договоре или интерфейсе.',
          'Документы на сайте могут обновляться. Актуальная редакция публикуется на этой странице и применяется с даты публикации, если в документе не указано иное.',
        ],
      },
    ],
    disclaimer:
      'Реквизиты добавлены по предоставленному документу. Перед коммерческим запуском документы стоит согласовать с юристом и обновить при изменении реквизитов.',
  },
  terms: {
    key: 'terms',
    title: 'Условия использования CODE9 Analytics',
    eyebrow: 'Terms of service',
    updatedAt: '24 апреля 2026',
    intro: [
      'Эти условия регулируют доступ к сайту, личному кабинету и функциям CODE9 Analytics.',
      'Используя сервис, пользователь подтверждает, что действует законно, имеет право подключать CRM-аккаунт и передавать данные для обработки в рамках выбранного тарифа или тестового режима.',
    ],
    sections: [
      {
        title: 'Исполнитель',
        body: [
          ...legalEntityRu,
          'Контакт для обращений по сервису, оплате и документам: support@aicode9.ru.',
        ],
      },
      {
        title: 'Регистрация и учетная запись',
        bullets: [
          'для работы с сервисом пользователь указывает email, пароль и данные рабочего пространства;',
          'пользователь отвечает за сохранность доступа к email, паролю и своей учетной записи;',
          'администратор рабочего пространства отвечает за приглашение сотрудников и права доступа внутри команды;',
          'CODE9 Analytics может ограничить доступ при нарушении условий, подозрении на компрометацию или незаконное использование.',
        ],
      },
      {
        title: 'CRM-подключения и выгрузка данных',
        body: [
          'Пользователь самостоятельно подключает amoCRM и выбирает период, воронки и объем выгрузки. Сервис может показывать предварительную оценку токенов, времени и объема данных до запуска операции.',
          'Данные клиента хранятся раздельно по рабочим пространствам и подключениям. Технические идентификаторы схем и подключений формируются сервером и не должны строиться из небезопасных пользовательских строк.',
        ],
        bullets: [
          'запрещено подключать CRM-аккаунты без права на такое подключение;',
          'запрещено выгружать данные, если это нарушает договоры с клиентами, закон или внутренние политики компании;',
          'пользователь отвечает за корректность выбранного периода, воронок и состава импортируемых данных.',
        ],
      },
      {
        title: 'Токены, тарифы и биллинг',
        body: [
          'AIC9-токены используются для учета операций выгрузки, обработки, AI-анализа и других функций сервиса. Конкретная стоимость операции показывается в личном кабинете до запуска, когда это технически возможно.',
          'Реальные списания и платежи применяются только после включения соответствующего платежного сценария и подтверждения пользователем. UI-заглушки, тестовые балансы и демо-операции не являются фактическим платежным обязательством.',
        ],
      },
      {
        title: 'Аналитика, отчеты и AI-функции',
        body: [
          'Дашборды и отчеты строятся на данных, которые были импортированы или синхронизированы в рамках выбранного подключения. Сервис не гарантирует полноту данных, если CRM API вернул неполный ответ, доступ был отозван или пользователь выбрал ограниченный период.',
          'AI-функции, транскрибация звонков и анализ коммуникаций включаются отдельными настройками и могут требовать дополнительного согласия, лимитов и политики конфиденциальности.',
        ],
      },
      {
        title: 'Support-доступ и администрирование',
        body: [
          'Founder/admin support mode может использоваться только для диагностики, поддержки клиента и контроля качества. Такой доступ должен быть ограничен уполномоченными администраторами, журналироваться и не использоваться для действий вне задачи поддержки.',
        ],
      },
      {
        title: 'Ответственность и доступность',
        body: [
          'Сервис предоставляется в пределах доступности инфраструктуры, CRM API и внешних провайдеров. CODE9 Analytics не отвечает за сбои amoCRM, ограничения API, действия хостинга, почтовых сервисов, Telegram или других внешних систем.',
          'Пользователь обязан самостоятельно проверять критичные отчеты и решения, принятые на основе аналитики сервиса.',
        ],
      },
    ],
    disclaimer:
      'Для публичной оферты нужно отдельно утвердить порядок оплаты, возвратов, SLA и применимое право.',
  },
  privacy: {
    key: 'privacy',
    title: 'Политика конфиденциальности CODE9 Analytics',
    eyebrow: 'Privacy policy',
    updatedAt: '24 апреля 2026',
    intro: [
      'Политика объясняет, какие данные CODE9 Analytics получает через сайт, личный кабинет, CRM-интеграции и технические журналы.',
      'Мы не публикуем пароли, access/refresh-токены, client_secret, коды авторизации и иные секреты в интерфейсе, логах или публичных API-ответах.',
    ],
    sections: [
      {
        title: 'Оператор персональных данных',
        body: [
          ...legalEntityRu,
          'Контакт для privacy-запросов и обращений субъектов персональных данных: support@aicode9.ru.',
        ],
      },
      {
        title: 'Какие данные обрабатываются',
        bullets: [
          'данные учетной записи: email, имя, язык интерфейса, признаки верификации и роли;',
          'данные рабочего пространства: название, участники, тариф, баланс AIC9-токенов и настройки уведомлений;',
          'технические данные CRM-подключения: провайдер, домен аккаунта, статус, время синхронизации, ошибки и служебные идентификаторы;',
          'CRM-данные, которые пользователь выбрал для выгрузки: сделки, контакты, компании, воронки, этапы, менеджеры и связанные события;',
          'технические журналы: IP-адрес, user-agent, время запросов, ошибки, события безопасности и действия администратора;',
          'cookies и session-идентификаторы, необходимые для входа, безопасности и работы личного кабинета.',
        ],
      },
      {
        title: 'Зачем нужны данные',
        bullets: [
          'создание учетной записи и защита доступа;',
          'подключение CRM и выполнение выбранных пользователем выгрузок;',
          'расчет токенов, прогресса, лимитов, истории операций и биллинговых записей;',
          'построение дашбордов, отчетов и уведомлений;',
          'диагностика ошибок, безопасность, предотвращение злоупотреблений и поддержка клиента;',
          'подготовка будущих AI-функций только после отдельного включения и согласования правил обработки.',
        ],
      },
      {
        title: 'Передача третьим лицам',
        body: [
          'Данные могут обрабатываться инфраструктурными провайдерами, почтовыми сервисами, CRM API, Telegram и платежными провайдерами только в объеме, необходимом для работы включенных функций.',
          'Список фактических провайдеров и условия трансграничной передачи должны быть утверждены перед коммерческим запуском и отражены в договоре или отдельном перечне внешних сервисов.',
        ],
      },
      {
        title: 'Хранение и защита',
        bullets: [
          'пароли и одноразовые коды должны храниться только в хешированном виде;',
          'токены интеграций и секреты должны храниться в зашифрованном виде;',
          'данные клиентов должны разделяться по рабочим пространствам и подключениям;',
          'административные действия и support-доступ должны журналироваться;',
          'удаление или ограничение обработки выполняется по запросу клиента и правилам, утвержденным для конкретного тарифа или договора.',
        ],
      },
      {
        title: 'Права пользователя',
        body: [
          'Пользователь может запросить доступ к своим данным, исправление, ограничение обработки, удаление или отзыв согласия, если это применимо по закону и договору.',
          'Запросы направляются на support@aicode9.ru. Для защиты данных мы можем запросить подтверждение личности или полномочий администратора рабочего пространства.',
        ],
      },
    ],
    disclaimer:
      'Перед запуском рекламы и продаж нужно проверить соответствие 152-ФЗ, cookie-уведомления, список обработчиков и требования рынков, где будут клиенты.',
  },
  personalData: {
    key: 'personalData',
    title: 'Обработка персональных данных',
    eyebrow: 'Personal data processing',
    updatedAt: '24 апреля 2026',
    intro: [
      'Этот документ описывает согласие пользователя на обработку персональных данных при регистрации, использовании личного кабинета и подключении CRM.',
      'Если пользователь подключает CRM компании, он подтверждает, что имеет право передавать соответствующие данные в CODE9 Analytics для обработки в рамках сервиса.',
    ],
    sections: [
      {
        title: 'Оператор персональных данных',
        body: [
          ...legalEntityRu,
          'Контакт для отзыва согласия, уточнения или удаления персональных данных: support@aicode9.ru.',
        ],
      },
      {
        title: 'Состав персональных данных',
        bullets: [
          'email, имя, должность или роль в рабочем пространстве;',
          'данные авторизации, события входа и параметры безопасности;',
          'служебные данные CRM-подключения и настройки рабочего пространства;',
          'данные физических лиц из CRM, если пользователь выбрал их для выгрузки: контакты, коммуникации, ответственные, события по сделкам;',
          'сообщения, письма, звонки или транскрипты только если соответствующие функции включены отдельно.',
        ],
      },
      {
        title: 'Цели обработки',
        bullets: [
          'предоставление доступа к сайту и личному кабинету;',
          'выполнение CRM-выгрузок и синхронизаций по выбору пользователя;',
          'создание аналитических отчетов, дашбордов и уведомлений;',
          'расчет токенов, тарифов, лимитов и истории операций;',
          'техническая поддержка, безопасность и расследование ошибок;',
          'выполнение требований закона, договора и запросов уполномоченных лиц.',
        ],
      },
      {
        title: 'Действия с данными',
        body: [
          'Обработка может включать сбор, запись, систематизацию, накопление, хранение, уточнение, извлечение, использование, передачу в рамках подключенных сервисов, обезличивание, блокирование, удаление и уничтожение.',
        ],
      },
      {
        title: 'Срок действия согласия',
        body: [
          'Согласие действует с момента регистрации или начала использования сервиса до его отзыва, удаления учетной записи или прекращения договора, если более длительное хранение не требуется законом, бухгалтерскими правилами, безопасностью или защитой прав.',
        ],
      },
      {
        title: 'Отзыв и удаление',
        body: [
          'Пользователь может отозвать согласие или запросить удаление данных через support@aicode9.ru. Если запрос касается CRM-данных компании, его должен направлять владелец или администратор соответствующего рабочего пространства.',
          'Активная автоматическая очистка tenant-данных, retention-политика и необратимое удаление включаются только после отдельного утверждения правил удаления.',
        ],
      },
    ],
    disclaimer:
      'Для production-версии нужно дополнительно утвердить основание обработки, перечень порученных обработчиков и применимые сроки хранения.',
  },
};

const enDocs: Record<LegalDocumentKey, LegalDocument> = {
  legal: {
    key: 'legal',
    title: 'CODE9 Analytics Legal Information',
    eyebrow: 'Legal / privacy / terms',
    updatedAt: 'April 24, 2026',
    intro: [
      'This section collects the core legal documents for the CODE9 Analytics website, client cabinet, CRM exports, dashboards, and future AI features.',
      'The service helps connect amoCRM, export selected CRM data into a client-specific data area, calculate AIC9 tokens, and build analytics.',
    ],
    related: [
      { title: 'Terms of Service', description: 'Rules for account access, CRM connections, exports, tokens, and analytics.', href: '/terms' },
      { title: 'Privacy Policy', description: 'What data is processed, why it is needed, and how it is protected.', href: '/privacy' },
      { title: 'Personal Data Processing', description: 'Consent and core rules for processing personal data.', href: '/personal-data' },
    ],
    sections: [
      {
        title: 'Service owner and contact',
        body: [
          ...legalEntityEn,
          ...legalEntityBankEn,
          'Legal, technical, and privacy contact: support@aicode9.ru.',
        ],
      },
      {
        title: 'Service scope',
        bullets: [
          'public website and login pages;',
          'client cabinet and admin cabinet;',
          'amoCRM connection and technical connection metadata;',
          'CRM exports, dashboards, reports, and AIC9 token estimates;',
          'notifications, operation logs, and future AI functionality.',
        ],
      },
      {
        title: 'Important limitations',
        body: [
          'Real payments, AI processing, integration token storage, and support access apply only in product modes that are explicitly enabled and described in the interface or contract.',
          'Documents may be updated. The current version is published on this page and applies from publication unless stated otherwise.',
        ],
      },
    ],
    disclaimer: 'Legal details were added from the provided document. Before commercial launch, have counsel review the documents and update them if the details change.',
  },
  terms: {
    key: 'terms',
    title: 'CODE9 Analytics Terms of Service',
    eyebrow: 'Terms of service',
    updatedAt: 'April 24, 2026',
    intro: [
      'These terms govern access to the CODE9 Analytics website, client cabinet, and product functionality.',
      'By using the service, the user confirms that they are authorized to connect the CRM account and process selected data through the service.',
    ],
    sections: [
      {
        title: 'Contractor',
        body: [
          ...legalEntityEn,
          'Service, payment, and document contact: support@aicode9.ru.',
        ],
      },
      {
        title: 'Account',
        bullets: [
          'the user provides an email, password, and workspace information;',
          'the user is responsible for protecting access to the account and email;',
          'workspace administrators manage team access and permissions;',
          'access may be restricted in case of abuse, compromise, or unlawful use.',
        ],
      },
      {
        title: 'CRM connections and exports',
        body: [
          'The user connects amoCRM and selects export periods, pipelines, and data scope. The service may show estimated tokens, duration, and data volume before an operation starts.',
          'Client data is separated by workspaces and connections. Technical schema and connection identifiers are generated by the server.',
        ],
      },
      {
        title: 'Tokens, plans, and billing',
        body: [
          'AIC9 tokens account for exports, processing, AI analysis, and other operations. The operation cost is shown in the cabinet before launch when technically possible.',
          'Real charges apply only after the relevant payment flow is enabled and confirmed by the user. UI placeholders, test balances, and demo operations are not payment obligations.',
        ],
      },
      {
        title: 'Analytics and AI features',
        body: [
          'Dashboards and reports are based on imported or synchronized data. Completeness depends on CRM API access, selected filters, and provider availability.',
          'AI analysis, call transcription, and communication analysis require separate settings and may require additional consent and processing rules.',
        ],
      },
      {
        title: 'Support access',
        body: [
          'Founder/admin support mode may be used only for diagnostics and customer support. Such access must be limited, logged, and used only for the support task.',
        ],
      },
    ],
    disclaimer: 'A commercial offer must separately approve payment/refund rules, SLA, and governing law.',
  },
  privacy: {
    key: 'privacy',
    title: 'CODE9 Analytics Privacy Policy',
    eyebrow: 'Privacy policy',
    updatedAt: 'April 24, 2026',
    intro: [
      'This policy explains what data CODE9 Analytics receives through the website, client cabinet, CRM integrations, and technical logs.',
      'Passwords, access/refresh tokens, client secrets, authorization codes, and other secrets must not be exposed in UI, logs, or public API responses.',
    ],
    sections: [
      {
        title: 'Personal data operator',
        body: [
          ...legalEntityEn,
          'Privacy and data subject requests: support@aicode9.ru.',
        ],
      },
      {
        title: 'Data we process',
        bullets: [
          'account data: email, name, language, verification flags, and roles;',
          'workspace data: name, members, plan, AIC9 token balance, and notification settings;',
          'CRM connection metadata: provider, account domain, status, sync time, errors, and service identifiers;',
          'selected CRM data: deals, contacts, companies, pipelines, stages, managers, and related events;',
          'technical logs: IP address, user-agent, request time, errors, security events, and admin actions;',
          'cookies and session identifiers required for login, security, and cabinet operation.',
        ],
      },
      {
        title: 'Purposes',
        bullets: [
          'account access and security;',
          'CRM connections and exports requested by the user;',
          'token estimates, progress, limits, operation history, and billing records;',
          'dashboards, reports, and notifications;',
          'error diagnostics, security, abuse prevention, and customer support;',
          'future AI functionality only after separate enablement and processing rules.',
        ],
      },
      {
        title: 'Subprocessors',
        body: [
          'Data may be processed by infrastructure providers, email services, CRM APIs, Telegram, and payment providers only as required for enabled features.',
          'The actual provider list and international transfer rules should be approved before commercial launch and reflected in the contract or a subprocessors list.',
        ],
      },
      {
        title: 'Protection',
        bullets: [
          'passwords and one-time codes are stored only as hashes;',
          'integration tokens and secrets are stored encrypted;',
          'client data is separated by workspace and connection;',
          'admin and support actions are logged;',
          'deletion or processing restriction is handled under the rules approved for the relevant plan or contract.',
        ],
      },
      {
        title: 'User rights',
        body: [
          'Users may request access, correction, restriction, deletion, or withdrawal of consent where applicable by law and contract.',
          'Requests should be sent to support@aicode9.ru. We may request identity or workspace-admin authority verification.',
        ],
      },
    ],
    disclaimer: 'Before advertising and sales, verify legal compliance for the target markets, cookie notices, subprocessors, and international transfers.',
  },
  personalData: {
    key: 'personalData',
    title: 'Personal Data Processing',
    eyebrow: 'Personal data processing',
    updatedAt: 'April 24, 2026',
    intro: [
      'This document describes user consent to personal data processing when registering, using the cabinet, and connecting CRM accounts.',
      'If a user connects a company CRM, they confirm they are authorized to transfer the relevant data to CODE9 Analytics for service processing.',
    ],
    sections: [
      {
        title: 'Personal data operator',
        body: [
          ...legalEntityEn,
          'Consent withdrawal, correction, and deletion requests: support@aicode9.ru.',
        ],
      },
      {
        title: 'Personal data categories',
        bullets: [
          'email, name, position, or workspace role;',
          'authentication data, login events, and security parameters;',
          'CRM connection metadata and workspace settings;',
          'personal data from CRM selected for export, including contacts, communications, responsible users, and deal events;',
          'messages, emails, calls, or transcripts only if those features are enabled separately.',
        ],
      },
      {
        title: 'Processing purposes',
        bullets: [
          'website and client cabinet access;',
          'CRM exports and synchronization requested by the user;',
          'analytics reports, dashboards, and notifications;',
          'token, plan, limit, and operation history accounting;',
          'support, security, and error investigation;',
          'legal and contractual compliance.',
        ],
      },
      {
        title: 'Processing actions',
        body: [
          'Processing may include collection, recording, organization, storage, updating, retrieval, use, transfer within enabled services, anonymization, blocking, deletion, and destruction.',
        ],
      },
      {
        title: 'Consent term and withdrawal',
        body: [
          'Consent applies from registration or first service use until withdrawal, account deletion, or contract termination unless longer storage is required by law, accounting, security, or legal defense.',
          'Withdrawal and deletion requests should be sent to support@aicode9.ru. Company CRM data requests must come from the owner or administrator of the relevant workspace.',
        ],
      },
    ],
    disclaimer: 'Production documents must additionally approve legal basis, subprocessors, and retention periods.',
  },
};

const esDocs: Record<LegalDocumentKey, LegalDocument> = {
  legal: {
    key: 'legal',
    title: 'Información legal de CODE9 Analytics',
    eyebrow: 'Legal / privacidad / términos',
    updatedAt: '24 de abril de 2026',
    intro: [
      'Esta sección reúne los documentos principales para el sitio web, el gabinete del cliente, las exportaciones CRM, los dashboards y futuras funciones de IA de CODE9 Analytics.',
      'El servicio ayuda a conectar amoCRM, exportar datos CRM seleccionados a un área separada del cliente, calcular tokens AIC9 y construir analítica.',
    ],
    related: [
      { title: 'Términos de servicio', description: 'Reglas de acceso, conexiones CRM, exportaciones, tokens y analítica.', href: '/terms' },
      { title: 'Política de privacidad', description: 'Qué datos se procesan, para qué se usan y cómo se protegen.', href: '/privacy' },
      { title: 'Tratamiento de datos personales', description: 'Consentimiento y reglas básicas de tratamiento de datos personales.', href: '/personal-data' },
    ],
    sections: [
      {
        title: 'Titular del servicio y contacto',
        body: [
          ...legalEntityEs,
          ...legalEntityBankEs,
          'Contacto legal, técnico y de privacidad: support@aicode9.ru.',
        ],
      },
      {
        title: 'Alcance del servicio',
        bullets: [
          'sitio público y páginas de acceso;',
          'gabinete del cliente y gabinete de administración;',
          'conexión amoCRM y metadatos técnicos de conexión;',
          'exportaciones CRM, dashboards, reportes y estimaciones de tokens AIC9;',
          'notificaciones, registros operativos y funciones futuras de IA.',
        ],
      },
      {
        title: 'Limitaciones importantes',
        body: [
          'Pagos reales, procesamiento de IA, almacenamiento de tokens de integración y acceso de soporte se aplican solo en modos activados explícitamente y descritos en la interfaz o contrato.',
          'Los documentos pueden actualizarse. La versión actual se publica en esta página y se aplica desde su publicación salvo indicación distinta.',
        ],
      },
    ],
    disclaimer: 'Los datos legales se añadieron desde el documento proporcionado. Antes del lanzamiento comercial, revise los documentos con asesoría legal y actualícelos si cambian los datos.',
  },
  terms: {
    key: 'terms',
    title: 'Términos de servicio de CODE9 Analytics',
    eyebrow: 'Términos de servicio',
    updatedAt: '24 de abril de 2026',
    intro: [
      'Estos términos regulan el acceso al sitio, al gabinete del cliente y a las funciones de CODE9 Analytics.',
      'Al usar el servicio, el usuario confirma que está autorizado para conectar la cuenta CRM y procesar los datos seleccionados mediante el servicio.',
    ],
    sections: [
      {
        title: 'Contratista',
        body: [
          ...legalEntityEs,
          'Contacto para servicio, pagos y documentos: support@aicode9.ru.',
        ],
      },
      {
        title: 'Cuenta',
        bullets: [
          'el usuario proporciona email, contraseña e información del workspace;',
          'el usuario es responsable de proteger el acceso a su cuenta y email;',
          'los administradores del workspace gestionan accesos y permisos del equipo;',
          'el acceso puede limitarse por abuso, compromiso de seguridad o uso ilegal.',
        ],
      },
      {
        title: 'Conexiones CRM y exportaciones',
        body: [
          'El usuario conecta amoCRM y selecciona periodos, embudos y alcance de exportación. El servicio puede mostrar estimaciones de tokens, duración y volumen antes de iniciar la operación.',
          'Los datos del cliente se separan por workspace y conexión. Los identificadores técnicos se generan en el servidor.',
        ],
      },
      {
        title: 'Tokens, planes y billing',
        body: [
          'Los tokens AIC9 contabilizan exportaciones, procesamiento, análisis de IA y otras operaciones. Cuando sea técnicamente posible, el coste se muestra antes del lanzamiento.',
          'Los cargos reales se aplican solo tras activar el flujo de pago correspondiente y la confirmación del usuario. Placeholders UI, balances de prueba y operaciones demo no son obligaciones de pago.',
        ],
      },
      {
        title: 'Analítica e IA',
        body: [
          'Dashboards y reportes se basan en datos importados o sincronizados. La completitud depende del acceso API CRM, filtros seleccionados y disponibilidad del proveedor.',
          'El análisis de IA, transcripción de llamadas y análisis de comunicaciones requieren configuración separada y pueden requerir consentimiento adicional.',
        ],
      },
      {
        title: 'Acceso de soporte',
        body: [
          'El modo founder/admin support puede utilizarse solo para diagnóstico y soporte. Debe ser limitado, registrado y usado únicamente para la tarea de soporte.',
        ],
      },
    ],
    disclaimer: 'Una oferta comercial debe aprobar por separado pagos, reembolsos, SLA y ley aplicable.',
  },
  privacy: {
    key: 'privacy',
    title: 'Política de privacidad de CODE9 Analytics',
    eyebrow: 'Política de privacidad',
    updatedAt: '24 de abril de 2026',
    intro: [
      'Esta política explica qué datos recibe CODE9 Analytics a través del sitio, gabinete, integraciones CRM y logs técnicos.',
      'Contraseñas, access/refresh tokens, client secrets, códigos de autorización y otros secretos no deben exponerse en UI, logs ni respuestas públicas API.',
    ],
    sections: [
      {
        title: 'Operador de datos personales',
        body: [
          ...legalEntityEs,
          'Solicitudes de privacidad y sujetos de datos: support@aicode9.ru.',
        ],
      },
      {
        title: 'Datos que procesamos',
        bullets: [
          'datos de cuenta: email, nombre, idioma, verificación y roles;',
          'datos del workspace: nombre, miembros, plan, balance de tokens AIC9 y notificaciones;',
          'metadatos de conexión CRM: proveedor, dominio, estado, tiempo de sincronización, errores e identificadores técnicos;',
          'datos CRM seleccionados: deals, contactos, compañías, embudos, etapas, managers y eventos relacionados;',
          'logs técnicos: IP, user-agent, tiempo de solicitud, errores, eventos de seguridad y acciones admin;',
          'cookies e identificadores de sesión necesarios para login, seguridad y gabinete.',
        ],
      },
      {
        title: 'Finalidades',
        bullets: [
          'acceso y seguridad de la cuenta;',
          'conexiones CRM y exportaciones solicitadas por el usuario;',
          'estimaciones de tokens, progreso, límites, historial y registros de billing;',
          'dashboards, reportes y notificaciones;',
          'diagnóstico de errores, seguridad, prevención de abuso y soporte;',
          'funciones futuras de IA solo tras habilitación separada y reglas de tratamiento.',
        ],
      },
      {
        title: 'Subprocesadores',
        body: [
          'Los datos pueden procesarse por proveedores de infraestructura, email, APIs CRM, Telegram y proveedores de pago solo en la medida necesaria para funciones activadas.',
          'La lista real de proveedores y reglas de transferencia internacional debe aprobarse antes del lanzamiento comercial.',
        ],
      },
      {
        title: 'Protección',
        bullets: [
          'contraseñas y códigos de un solo uso se almacenan como hashes;',
          'tokens y secretos de integración se almacenan cifrados;',
          'los datos de clientes se separan por workspace y conexión;',
          'acciones admin y soporte se registran;',
          'eliminación o restricción de tratamiento se gestiona según reglas aprobadas para el plan o contrato.',
        ],
      },
      {
        title: 'Derechos del usuario',
        body: [
          'Los usuarios pueden solicitar acceso, corrección, restricción, eliminación o retirada del consentimiento cuando aplique por ley y contrato.',
          'Las solicitudes deben enviarse a support@aicode9.ru. Podemos pedir verificación de identidad o autoridad admin del workspace.',
        ],
      },
    ],
    disclaimer: 'Antes de publicidad y ventas, verifique cumplimiento legal para mercados objetivo, cookies, subprocesadores y transferencias internacionales.',
  },
  personalData: {
    key: 'personalData',
    title: 'Tratamiento de datos personales',
    eyebrow: 'Tratamiento de datos personales',
    updatedAt: '24 de abril de 2026',
    intro: [
      'Este documento describe el consentimiento del usuario para el tratamiento de datos personales al registrarse, usar el gabinete y conectar cuentas CRM.',
      'Si el usuario conecta un CRM de empresa, confirma que está autorizado para transferir los datos correspondientes a CODE9 Analytics para el procesamiento del servicio.',
    ],
    sections: [
      {
        title: 'Operador de datos personales',
        body: [
          ...legalEntityEs,
          'Solicitudes de retirada del consentimiento, corrección y eliminación: support@aicode9.ru.',
        ],
      },
      {
        title: 'Categorías de datos personales',
        bullets: [
          'email, nombre, cargo o rol en el workspace;',
          'datos de autenticación, eventos de login y parámetros de seguridad;',
          'metadatos de conexión CRM y configuración del workspace;',
          'datos personales desde CRM seleccionados para exportación: contactos, comunicaciones, responsables y eventos de deals;',
          'mensajes, emails, llamadas o transcripciones solo si esas funciones se activan por separado.',
        ],
      },
      {
        title: 'Finalidades del tratamiento',
        bullets: [
          'acceso al sitio y gabinete;',
          'exportaciones CRM y sincronización solicitadas por el usuario;',
          'reportes analíticos, dashboards y notificaciones;',
          'contabilidad de tokens, planes, límites e historial;',
          'soporte, seguridad e investigación de errores;',
          'cumplimiento legal y contractual.',
        ],
      },
      {
        title: 'Acciones de tratamiento',
        body: [
          'El tratamiento puede incluir recopilación, registro, organización, almacenamiento, actualización, recuperación, uso, transferencia dentro de servicios activados, anonimización, bloqueo, eliminación y destrucción.',
        ],
      },
      {
        title: 'Vigencia y retirada',
        body: [
          'El consentimiento aplica desde el registro o primer uso hasta su retirada, eliminación de cuenta o terminación del contrato, salvo almacenamiento más largo requerido por ley, contabilidad, seguridad o defensa legal.',
          'Solicitudes de retirada o eliminación: support@aicode9.ru. Las solicitudes sobre datos CRM de empresa deben venir del propietario o administrador del workspace.',
        ],
      },
    ],
    disclaimer: 'Los documentos de producción deben aprobar adicionalmente base legal, subprocesadores y periodos de retención.',
  },
};

const legalDocumentsByLocale: Record<Locale, Record<LegalDocumentKey, LegalDocument>> = {
  ru: ruDocs,
  en: enDocs,
  es: esDocs,
};

function resolveLocale(locale: string): Locale {
  if (locale === 'en' || locale === 'es' || locale === 'ru') return locale;
  return 'ru';
}

export function getLegalDocument(locale: string, key: LegalDocumentKey): LegalDocument {
  return legalDocumentsByLocale[resolveLocale(locale)][key];
}
