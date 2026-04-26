'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocale } from 'next-intl';
import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  FileText,
  MessageSquareText,
  PhoneCall,
  ShieldCheck,
  UserRound,
  Workflow,
} from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { api } from '@/lib/api';
import { isCustomerVisibleCrmConnection } from '@/lib/connectionVisibility';
import { cn } from '@/lib/utils';
import type { CrmConnection } from '@/lib/types';

type ScenarioKey =
  | 'invoice'
  | 'callback'
  | 'proposal'
  | 'price'
  | 'discount'
  | 'stock'
  | 'delivery'
  | 'requisites'
  | 'payment'
  | 'reschedule'
  | 'consultation'
  | 'human'
  | 'return'
  | 'complaint'
  | 'decline'
  | 'no_response';

interface ScenarioPreset {
  key: ScenarioKey;
  title: string;
  short: string;
  icon: 'invoice' | 'phone' | 'proposal' | 'message' | 'risk' | 'human';
  conditions: string[];
  actions: Array<{ label: string; recommended?: boolean; risky?: boolean }>;
  message: string;
  riskMode: 'manager_approval' | 'auto_draft' | 'high_priority';
}

type StageScopeState = Record<ScenarioKey, string[]>;

interface ExportStage {
  id: string;
  name: string;
  sort_order?: number | null;
}

interface ExportPipeline {
  id: string;
  name: string;
  stages: ExportStage[];
}

interface ExportOptions {
  connection_id: string;
  pipelines: ExportPipeline[];
  source?: string;
  empty_reason?: string | null;
  active_pipeline_ids?: string[];
}

const SCENARIOS: ScenarioPreset[] = [
  {
    key: 'invoice',
    title: 'Выставить счет',
    short: 'Товар, цена, реквизиты, счет и этап сделки.',
    icon: 'invoice',
    conditions: ['Товар найден в базе', 'Цена совпадает с озвученной', 'Есть реквизиты клиента'],
    actions: [
      { label: 'Проверить товар в базе', recommended: true },
      { label: 'Сверить цену', recommended: true },
      { label: 'Создать счет', recommended: true },
      { label: 'Перевести сделку на этап "Счет"', recommended: true },
      { label: 'Поставить задачу менеджеру "Проверить счет"', recommended: true },
      { label: 'Отправить счет клиенту автоматически', risky: true },
    ],
    message: 'Счет подготовили, сейчас менеджер проверит и отправит.',
    riskMode: 'manager_approval',
  },
  {
    key: 'callback',
    title: 'Перезвонить',
    short: 'Создать задачу на звонок и зафиксировать время.',
    icon: 'phone',
    conditions: ['Клиент оставил время или окно для звонка', 'В сделке есть ответственный менеджер'],
    actions: [
      { label: 'Создать задачу менеджеру', recommended: true },
      { label: 'Поставить дату и время звонка', recommended: true },
      { label: 'Перевести сделку на этап "Нужен звонок"', recommended: true },
      { label: 'Отправить клиенту подтверждение времени', recommended: true },
    ],
    message: 'Хорошо, передали менеджеру. Он свяжется с вами в указанное время.',
    riskMode: 'auto_draft',
  },
  {
    key: 'proposal',
    title: 'Получить КП',
    short: 'Собрать КП из шаблона и поставить проверку.',
    icon: 'proposal',
    conditions: ['Понятен продукт или услуга', 'Есть шаблон КП', 'Есть контакт клиента'],
    actions: [
      { label: 'Собрать КП из шаблона', recommended: true },
      { label: 'Прикрепить КП к сделке', recommended: true },
      { label: 'Поставить задачу менеджеру "Проверить КП"', recommended: true },
      { label: 'Перевести сделку на этап "КП"', recommended: true },
      { label: 'Отправить КП клиенту автоматически', risky: true },
    ],
    message: 'Коммерческое предложение подготовим и отправим после проверки менеджером.',
    riskMode: 'manager_approval',
  },
  {
    key: 'price',
    title: 'Узнать цену',
    short: 'Найти позицию, показать цену или уточнить данные.',
    icon: 'message',
    conditions: ['Клиент назвал товар или услугу', 'Есть прайс или база товаров'],
    actions: [
      { label: 'Найти товар или услугу в базе', recommended: true },
      { label: 'Показать менеджеру найденную цену', recommended: true },
      { label: 'Если данных мало — задать уточняющий вопрос', recommended: true },
    ],
    message: 'Сейчас проверим цену. Если потребуется уточнение, менеджер задаст один короткий вопрос.',
    riskMode: 'auto_draft',
  },
  {
    key: 'discount',
    title: 'Получить скидку',
    short: 'Проверить лимит скидки и эскалировать риск.',
    icon: 'risk',
    conditions: ['Понятна сумма сделки', 'Настроен лимит скидки', 'Известна маржа или минимальная цена'],
    actions: [
      { label: 'Проверить лимит скидки', recommended: true },
      { label: 'Проверить маржу', recommended: true },
      { label: 'Если выше лимита — задача руководителю', recommended: true },
      { label: 'Подготовить аккуратный ответ клиенту', recommended: true },
    ],
    message: 'Проверим возможность скидки и вернемся с подтверждением.',
    riskMode: 'manager_approval',
  },
  {
    key: 'stock',
    title: 'Проверить наличие',
    short: 'Проверить склад или поставить уточнение.',
    icon: 'message',
    conditions: ['Клиент назвал позицию', 'Подключена база товаров или склад'],
    actions: [
      { label: 'Проверить наличие в базе', recommended: true },
      { label: 'Если нет данных — задача уточнить склад', recommended: true },
      { label: 'Подготовить ответ клиенту', recommended: true },
    ],
    message: 'Сейчас проверим наличие и сообщим точный статус.',
    riskMode: 'auto_draft',
  },
  {
    key: 'delivery',
    title: 'Уточнить доставку',
    short: 'Город, способ, срок и стоимость доставки.',
    icon: 'message',
    conditions: ['Известен город доставки', 'Понятен товар или объем заказа'],
    actions: [
      { label: 'Проверить город доставки', recommended: true },
      { label: 'Рассчитать срок и стоимость', recommended: true },
      { label: 'Поставить задачу, если нужен ручной расчет', recommended: true },
    ],
    message: 'Уточним доставку и вернемся с точными сроками и стоимостью.',
    riskMode: 'auto_draft',
  },
  {
    key: 'requisites',
    title: 'Отправить реквизиты',
    short: 'Распознать компанию и обновить карточку.',
    icon: 'invoice',
    conditions: ['Клиент отправил ИНН или реквизиты', 'Компания найдена через DaData или CRM'],
    actions: [
      { label: 'Распознать ИНН или компанию', recommended: true },
      { label: 'Обновить карточку клиента', recommended: true },
      { label: 'Продолжить сценарий выставления счета', recommended: true },
    ],
    message: 'Реквизиты получили, обновим карточку и продолжим оформление.',
    riskMode: 'auto_draft',
  },
  {
    key: 'payment',
    title: 'Оплатить заказ',
    short: 'Проверить счет и перевести в ожидание оплаты.',
    icon: 'invoice',
    conditions: ['Счет создан', 'Сумма счета совпадает со сделкой'],
    actions: [
      { label: 'Проверить счет', recommended: true },
      { label: 'Подготовить ссылку или инструкцию на оплату', recommended: true },
      { label: 'Перевести сделку на этап "Ожидание оплаты"', recommended: true },
      { label: 'Отправить платежную ссылку автоматически', risky: true },
    ],
    message: 'Подготовили оплату. Менеджер проверит и отправит вам ссылку или инструкцию.',
    riskMode: 'manager_approval',
  },
  {
    key: 'reschedule',
    title: 'Перенести встречу',
    short: 'Переставить задачу или встречу.',
    icon: 'phone',
    conditions: ['Клиент предложил новую дату или время', 'Есть активная встреча или задача'],
    actions: [
      { label: 'Создать новую задачу или встречу', recommended: true },
      { label: 'Закрыть старую задачу как перенесенную', recommended: true },
      { label: 'Отправить подтверждение клиенту', recommended: true },
    ],
    message: 'Перенесли встречу, менеджер подтвердит новое время.',
    riskMode: 'auto_draft',
  },
  {
    key: 'consultation',
    title: 'Получить консультацию',
    short: 'Передать менеджеру с контекстом вопроса.',
    icon: 'human',
    conditions: ['Клиент задал вопрос по продукту', 'Есть ответственный менеджер'],
    actions: [
      { label: 'Собрать краткий контекст вопроса', recommended: true },
      { label: 'Поставить задачу менеджеру', recommended: true },
      { label: 'Подготовить черновик ответа', recommended: true },
    ],
    message: 'Передали вопрос менеджеру, он вернется с консультацией.',
    riskMode: 'auto_draft',
  },
  {
    key: 'human',
    title: 'Поговорить с живым менеджером',
    short: 'Остановить автологику и передать человеку.',
    icon: 'human',
    conditions: ['Клиент явно просит человека', 'Есть ответственный или дежурный менеджер'],
    actions: [
      { label: 'Остановить автоответы по диалогу', recommended: true },
      { label: 'Поставить срочную задачу менеджеру', recommended: true },
      { label: 'Уведомить в Telegram/MAX', recommended: true },
    ],
    message: 'Передали живому менеджеру. Он подключится к диалогу.',
    riskMode: 'high_priority',
  },
  {
    key: 'return',
    title: 'Оформить возврат',
    short: 'Передать в поддержку и зафиксировать причину.',
    icon: 'risk',
    conditions: ['Клиент просит возврат', 'Есть номер заказа или сделки'],
    actions: [
      { label: 'Зафиксировать причину возврата', recommended: true },
      { label: 'Поставить задачу поддержке', recommended: true },
      { label: 'Уведомить руководителя', recommended: true },
    ],
    message: 'Зафиксировали запрос на возврат, передали ответственному специалисту.',
    riskMode: 'high_priority',
  },
  {
    key: 'complaint',
    title: 'Пожаловаться',
    short: 'Высокий приоритет, поддержка, руководитель.',
    icon: 'risk',
    conditions: ['Есть негатив или претензия', 'Можно определить сделку или клиента'],
    actions: [
      { label: 'Поставить высокий приоритет', recommended: true },
      { label: 'Перевести в поддержку', recommended: true },
      { label: 'Уведомить руководителя', recommended: true },
      { label: 'Подготовить спокойный ответ клиенту', recommended: true },
    ],
    message: 'Спасибо, что написали. Передали вопрос руководителю и ответственному специалисту.',
    riskMode: 'high_priority',
  },
  {
    key: 'decline',
    title: 'Отказаться',
    short: 'Причина отказа и потеряно или возврат позже.',
    icon: 'risk',
    conditions: ['Клиент явно отказался', 'Причина отказа понятна или её можно уточнить'],
    actions: [
      { label: 'Зафиксировать причину отказа', recommended: true },
      { label: 'Перевести в "Потеряно" после подтверждения', risky: true },
      { label: 'Поставить задачу вернуться позже', recommended: true },
    ],
    message: 'Поняли. Зафиксируем причину и, если будет уместно, вернемся позже.',
    riskMode: 'manager_approval',
  },
  {
    key: 'no_response',
    title: 'Нет ответа',
    short: 'Follow-up и повторная задача.',
    icon: 'message',
    conditions: ['Нет ответа дольше заданного времени', 'Сделка не закрыта'],
    actions: [
      { label: 'Создать follow-up', recommended: true },
      { label: 'Подготовить мягкое сообщение', recommended: true },
      { label: 'Поставить повторную задачу', recommended: true },
      { label: 'Уведомить менеджера при повторном молчании', recommended: true },
    ],
    message: 'Здравствуйте! Подскажите, актуален ли еще вопрос? Готовы помочь.',
    riskMode: 'auto_draft',
  },
];

const COPY = {
  ru: {
    badge: 'Безопасный конструктор',
    title: 'AI-автодействия',
    subtitle:
      'Настройте, что CODE9 должен делать, когда клиент просит счет, звонок, КП или живого менеджера. На этом этапе действия сохраняются как правило-черновик и не запускают реальные отправки.',
    when: 'Когда',
    clientWants: 'Клиент хочет',
    contextTitle: 'Контекст, который проверяет система',
    contextItems: ['CRM-сделка и этап', 'Ответственный менеджер', 'История переписки', 'Почта и сообщения', 'Товары / услуги', 'Прайс и скидки', 'Реквизиты и ИНН'],
    conditions: 'Условия',
    actions: 'Что сделать',
    message: 'Сообщение клиенту',
    risk: 'Если есть риск',
    save: 'Сохранить действие',
    cancel: 'Сбросить',
    selectedRule: 'Предпросмотр правила',
    safeTitle: 'Режим первого запуска',
    safeBody:
      'Реальное создание задач в amoCRM, отправка сообщений, счетов и списание токенов будут включены отдельным GO. Сейчас это интерфейс настройки и будущий контракт поведения.',
    savedTitle: 'Правило сохранено в черновик',
    savedBody: 'Пока без запуска реальных действий. Следующий шаг — backend-хранение правил и журнал срабатываний.',
    riskModes: {
      manager_approval: 'Попросить подтверждение менеджера',
      auto_draft: 'Создать черновик без отправки',
      high_priority: 'Высокий приоритет и уведомление руководителю',
    },
    statuses: {
      recommended: 'рекомендуется',
      risky: 'только после GO',
    },
    stages: {
      metric: 'Этапов',
      title: 'Работает на этапах amoCRM',
      subtitle:
        'Выберите реальные воронки и этапы из подключенной amoCRM. Правило будет срабатывать только там, где вы поставили галочки.',
      connection: 'Подключение',
      loadingConnections: 'Загружаем подключения…',
      connectionError: 'Не удалось загрузить подключения.',
      noWorkspace: 'Workspace еще не найден. Откройте кабинет после входа в аккаунт.',
      noConnection: 'Сначала подключите amoCRM, чтобы выбрать реальные этапы.',
      loading: 'Загружаем воронки и этапы из amoCRM…',
      loadError: 'Не удалось загрузить воронки и этапы.',
      empty: 'В tenant-cache пока нет реальных воронок. Запустите синхронизацию или выгрузку amoCRM.',
      selected: 'Выбрано этапов',
      selectedChips: 'Выбранные этапы',
      noneSelected: 'Этапы не выбраны',
      noneSelectedShort: 'не выбраны',
      dropdownLabel: 'Где работает',
      dropdownPlaceholder: 'Выберите этапы amoCRM',
      selectAll: 'Выбрать все',
      clearAll: 'Убрать все',
      visibleScopeHint: 'Показываем только воронки, выбранные в активной выгрузке amoCRM.',
      previewLabel: 'Этапы amoCRM',
      allPipelineStages: 'Все этапы воронки',
      clear: 'Очистить',
      ruleDisabled: 'Выберите хотя бы один этап amoCRM. Так автодействие не будет работать во всех воронках сразу.',
    },
  },
  en: {
    badge: 'Safe builder',
    title: 'AI auto-actions',
    subtitle:
      'Configure what CODE9 should do when a client asks for an invoice, callback, proposal or a human manager. This phase saves a draft rule and does not execute real actions.',
    when: 'When',
    clientWants: 'Client wants',
    contextTitle: 'Context checked by the system',
    contextItems: ['CRM deal and stage', 'Responsible manager', 'Message history', 'Email and chats', 'Products / services', 'Prices and discounts', 'Company details and tax ID'],
    conditions: 'Conditions',
    actions: 'What to do',
    message: 'Client message',
    risk: 'If there is risk',
    save: 'Save action',
    cancel: 'Reset',
    selectedRule: 'Rule preview',
    safeTitle: 'First launch mode',
    safeBody:
      'Real amoCRM task creation, message sending, invoice sending and token charging require a separate GO. For now this is a configuration interface and future behavior contract.',
    savedTitle: 'Rule saved as draft',
    savedBody: 'No real action was executed. Next step is backend rule storage and execution log.',
    riskModes: {
      manager_approval: 'Ask manager for approval',
      auto_draft: 'Create draft without sending',
      high_priority: 'High priority and owner alert',
    },
    statuses: {
      recommended: 'recommended',
      risky: 'separate GO',
    },
    stages: {
      metric: 'Stages',
      title: 'Works on amoCRM stages',
      subtitle:
        'Select real pipelines and stages from the connected amoCRM account. The rule will trigger only where you check it.',
      connection: 'Connection',
      loadingConnections: 'Loading connections…',
      connectionError: 'Failed to load connections.',
      noWorkspace: 'Workspace is not available yet. Open the cabinet after signing in.',
      noConnection: 'Connect amoCRM first to choose real stages.',
      loading: 'Loading pipelines and stages from amoCRM…',
      loadError: 'Failed to load pipelines and stages.',
      empty: 'No real pipelines are cached yet. Run amoCRM sync or export first.',
      selected: 'Stages selected',
      selectedChips: 'Selected stages',
      noneSelected: 'No stages selected',
      noneSelectedShort: 'none',
      dropdownLabel: 'Where it works',
      dropdownPlaceholder: 'Choose amoCRM stages',
      selectAll: 'Select all',
      clearAll: 'Clear all',
      visibleScopeHint: 'Only pipelines selected in the active amoCRM export are shown.',
      previewLabel: 'amoCRM stages',
      allPipelineStages: 'All pipeline stages',
      clear: 'Clear',
      ruleDisabled: 'Select at least one amoCRM stage. This prevents an auto-action from running everywhere.',
    },
  },
  es: {
    badge: 'Constructor seguro',
    title: 'Acciones automáticas IA',
    subtitle:
      'Configura qué debe hacer CODE9 cuando el cliente pide factura, llamada, propuesta o un manager humano. Esta fase guarda una regla borrador y no ejecuta acciones reales.',
    when: 'Cuando',
    clientWants: 'El cliente quiere',
    contextTitle: 'Contexto que revisa el sistema',
    contextItems: ['Deal y etapa CRM', 'Manager responsable', 'Historial de mensajes', 'Email y chats', 'Productos / servicios', 'Precios y descuentos', 'Datos fiscales'],
    conditions: 'Condiciones',
    actions: 'Qué hacer',
    message: 'Mensaje al cliente',
    risk: 'Si hay riesgo',
    save: 'Guardar acción',
    cancel: 'Restablecer',
    selectedRule: 'Vista previa',
    safeTitle: 'Modo de primer lanzamiento',
    safeBody:
      'Crear tareas reales en amoCRM, enviar mensajes/facturas y cobrar tokens requiere un GO separado. Ahora es interfaz de configuración y contrato futuro.',
    savedTitle: 'Regla guardada como borrador',
    savedBody: 'No se ejecutó ninguna acción real. El siguiente paso es guardar reglas en backend y log de ejecuciones.',
    riskModes: {
      manager_approval: 'Pedir aprobación del manager',
      auto_draft: 'Crear borrador sin enviar',
      high_priority: 'Alta prioridad y alerta al dueño',
    },
    statuses: {
      recommended: 'recomendado',
      risky: 'GO separado',
    },
    stages: {
      metric: 'Etapas',
      title: 'Funciona en etapas amoCRM',
      subtitle:
        'Selecciona pipelines y etapas reales de la cuenta amoCRM conectada. La regla se activará solo donde marques.',
      connection: 'Conexión',
      loadingConnections: 'Cargando conexiones…',
      connectionError: 'No se pudieron cargar las conexiones.',
      noWorkspace: 'Workspace no disponible todavía. Abre el gabinete después de iniciar sesión.',
      noConnection: 'Conecta amoCRM primero para elegir etapas reales.',
      loading: 'Cargando pipelines y etapas desde amoCRM…',
      loadError: 'No se pudieron cargar pipelines y etapas.',
      empty: 'Todavía no hay pipelines reales en cache. Ejecuta sync o export amoCRM.',
      selected: 'Etapas seleccionadas',
      selectedChips: 'Etapas seleccionadas',
      noneSelected: 'No hay etapas seleccionadas',
      noneSelectedShort: 'ninguna',
      dropdownLabel: 'Dónde funciona',
      dropdownPlaceholder: 'Elegir etapas amoCRM',
      selectAll: 'Seleccionar todo',
      clearAll: 'Quitar todo',
      visibleScopeHint: 'Solo se muestran pipelines seleccionados en la exportación amoCRM activa.',
      previewLabel: 'Etapas amoCRM',
      allPipelineStages: 'Todas las etapas del pipeline',
      clear: 'Limpiar',
      ruleDisabled: 'Selecciona al menos una etapa amoCRM. Así la acción no funcionará en todos lados.',
    },
  },
};

const iconMap = {
  invoice: FileText,
  phone: PhoneCall,
  proposal: ClipboardCheck,
  message: MessageSquareText,
  risk: AlertTriangle,
  human: UserRound,
};

const MVP_KEYS: ScenarioKey[] = ['invoice', 'callback', 'proposal', 'no_response', 'human'];

function createEmptyStageScope(): StageScopeState {
  const scope = {} as StageScopeState;
  SCENARIOS.forEach((scenario) => {
    scope[scenario.key] = [];
  });
  return scope;
}

type StageCopy = typeof COPY.ru.stages;

export default function AiActionsPage() {
  const locale = useLocale();
  const { user, ready } = useUserAuth();
  const copy = COPY[locale as keyof typeof COPY] ?? COPY.ru;
  const workspaceId = user?.workspaces?.[0]?.id ?? null;
  const [selectedKey, setSelectedKey] = useState<ScenarioKey>('invoice');
  const selected = SCENARIOS.find((item) => item.key === selectedKey) ?? SCENARIOS[0];
  const [conditions, setConditions] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(selected.conditions.map((item) => [item, true])),
  );
  const [actions, setActions] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(selected.actions.map((item) => [item.label, Boolean(item.recommended)])),
  );
  const [message, setMessage] = useState(selected.message);
  const [riskMode, setRiskMode] = useState(selected.riskMode);
  const [saved, setSaved] = useState(false);
  const [connections, setConnections] = useState<CrmConnection[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null);
  const [connectionsLoading, setConnectionsLoading] = useState(false);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [exportOptions, setExportOptions] = useState<ExportOptions | null>(null);
  const [stagesLoading, setStagesLoading] = useState(false);
  const [stagesError, setStagesError] = useState<string | null>(null);
  const [stageScope, setStageScope] = useState<StageScopeState>(() => createEmptyStageScope());

  const selectedConditionsCount = useMemo(
    () => Object.values(conditions).filter(Boolean).length,
    [conditions],
  );
  const selectedActionsCount = useMemo(() => Object.values(actions).filter(Boolean).length, [actions]);
  const selectedConnection = connections.find((connection) => connection.id === selectedConnectionId) ?? null;
  const visibleExportOptions = useMemo(
    () => filterExportOptionsByActiveExport(exportOptions, selectedConnection),
    [exportOptions, selectedConnection],
  );
  const visibleStageIds = useMemo(() => collectStageIds(visibleExportOptions), [visibleExportOptions]);
  const selectedStageIds = useMemo(
    () => restrictStageIds(stageScope[selectedKey] ?? [], visibleStageIds),
    [selectedKey, stageScope, visibleStageIds],
  );
  const selectedStageCount = selectedStageIds.length;
  const canSaveRule = selectedStageCount > 0;
  const selectedStageNames = useMemo(
    () => selectedStageLabels(visibleExportOptions, selectedStageIds),
    [visibleExportOptions, selectedStageIds],
  );

  useEffect(() => {
    if (!visibleExportOptions) return;
    const allowed = new Set(visibleStageIds);
    setStageScope((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const scenario of SCENARIOS) {
        const current = prev[scenario.key] ?? [];
        const filtered = current.filter((stageId) => allowed.has(stageId));
        if (filtered.length !== current.length) {
          changed = true;
          next[scenario.key] = filtered;
        }
      }
      return changed ? next : prev;
    });
  }, [visibleExportOptions, visibleStageIds]);

  useEffect(() => {
    let cancelled = false;
    setConnections([]);
    setSelectedConnectionId(null);
    setConnectionsError(null);
    if (!ready || !workspaceId) return;

    setConnectionsLoading(true);
    api
      .get<CrmConnection[]>(`/workspaces/${workspaceId}/crm/connections`)
      .then((items) => {
        if (cancelled) return;
        const visibleItems = items.filter(isCustomerVisibleCrmConnection);
        setConnections(visibleItems);
        const activeConnection =
          visibleItems.find((connection) => connection.provider === 'amocrm' && connection.status === 'active') ??
          visibleItems.find((connection) => connection.provider === 'amocrm') ??
          visibleItems[0] ??
          null;
        setSelectedConnectionId(activeConnection?.id ?? null);
      })
      .catch(() => {
        if (!cancelled) setConnectionsError(copy.stages.connectionError);
      })
      .finally(() => {
        if (!cancelled) setConnectionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [copy.stages.connectionError, ready, workspaceId]);

  useEffect(() => {
    let cancelled = false;
    setExportOptions(null);
    setStagesError(null);
    if (!selectedConnectionId) return;

    setStagesLoading(true);
    api
      .get<ExportOptions>(`/crm/connections/${selectedConnectionId}/export/options`)
      .then((options) => {
        if (!cancelled) setExportOptions(normalizeExportOptions(options));
      })
      .catch(() => {
        if (!cancelled) setStagesError(copy.stages.loadError);
      })
      .finally(() => {
        if (!cancelled) setStagesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [copy.stages.loadError, selectedConnectionId]);

  const selectScenario = (key: ScenarioKey) => {
    const preset = SCENARIOS.find((item) => item.key === key) ?? SCENARIOS[0];
    setSelectedKey(key);
    setConditions(Object.fromEntries(preset.conditions.map((item) => [item, true])));
    setActions(Object.fromEntries(preset.actions.map((item) => [item.label, Boolean(item.recommended)])));
    setMessage(preset.message);
    setRiskMode(preset.riskMode);
    setSaved(false);
  };

  const resetCurrent = () => selectScenario(selectedKey);
  const updateCurrentStageScope = (nextStageIds: string[]) => {
    setStageScope((prev) => ({ ...prev, [selectedKey]: nextStageIds }));
    setSaved(false);
  };
  const toggleStage = (stageId: string) => {
    const current = new Set(selectedStageIds);
    if (current.has(stageId)) {
      current.delete(stageId);
    } else {
      current.add(stageId);
    }
    updateCurrentStageScope(Array.from(current));
  };
  const togglePipeline = (pipeline: ExportPipeline) => {
    const stageIds = pipeline.stages.map((stage) => stage.id);
    if (!stageIds.length) return;

    const current = new Set(selectedStageIds);
    const allSelected = stageIds.every((stageId) => current.has(stageId));
    stageIds.forEach((stageId) => {
      if (allSelected) {
        current.delete(stageId);
      } else {
        current.add(stageId);
      }
    });
    updateCurrentStageScope(Array.from(current));
  };
  const clearCurrentStageScope = () => updateCurrentStageScope([]);
  const selectAllCurrentStageScope = () => updateCurrentStageScope(visibleStageIds);
  const Icon = iconMap[selected.icon];

  return (
    <div className="space-y-6">
      <header className="cabinet-page-hero rounded-2xl border border-border p-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-4xl">
            <Badge tone="info">{copy.badge}</Badge>
            <div className="mt-4 flex items-start gap-4">
              <div className="rounded-2xl bg-primary/10 p-3 text-primary">
                <Workflow className="h-7 w-7" />
              </div>
              <div>
                <h1 className="text-3xl font-semibold tracking-tight text-foreground">{copy.title}</h1>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.subtitle}</p>
              </div>
            </div>
          </div>
          <div className="grid min-w-[260px] gap-2 text-sm">
            <MetricPill label={copy.conditions} value={String(selectedConditionsCount)} />
            <MetricPill label={copy.actions} value={String(selectedActionsCount)} />
            <MetricPill label={copy.stages.metric} value={String(selectedStageCount)} />
          </div>
        </div>
      </header>

      <section className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
          <div className="card p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{copy.when}</div>
            <label className="mt-3 block text-sm font-medium">
              {copy.clientWants}
              <div className="relative mt-2">
                <select
                  className="block w-full appearance-none rounded-xl border border-border bg-white px-3 py-3 pr-10 text-sm font-medium text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                  value={selectedKey}
                  onChange={(event) => selectScenario(event.target.value as ScenarioKey)}
                >
                  {SCENARIOS.map((scenario) => (
                    <option key={scenario.key} value={scenario.key}>
                      {scenario.title}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-3.5 h-4 w-4 text-muted-foreground" />
              </div>
            </label>
          </div>

          <div className="card p-4">
            <h2 className="font-semibold">{copy.contextTitle}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {copy.contextItems.map((item) => (
                <Badge key={item} tone="neutral">
                  {item}
                </Badge>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h2 className="font-semibold">MVP</h2>
            <div className="mt-3 grid gap-2">
              {MVP_KEYS.map((key) => {
                const preset = SCENARIOS.find((item) => item.key === key);
                if (!preset) return null;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => selectScenario(key)}
                    className={cn(
                      'rounded-xl border px-3 py-2 text-left text-sm transition',
                      selectedKey === key ? 'border-primary bg-primary/10 text-foreground' : 'border-border bg-white text-muted-foreground hover:border-primary',
                    )}
                  >
                    {preset.title}
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        <main className="space-y-6">
          <section className="card overflow-hidden">
            <div className="border-b border-border bg-muted/40 p-5">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-primary/10 p-2 text-primary">
                    <Icon className="h-6 w-6" />
                  </div>
                  <div>
                    <h2 className="text-xl font-semibold">{selected.title}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">{selected.short}</p>
                  </div>
                </div>
                <Badge tone={selected.riskMode === 'high_priority' ? 'warning' : 'neutral'}>
                  {copy.riskModes[selected.riskMode]}
                </Badge>
              </div>
            </div>

            <div className="grid gap-0 lg:grid-cols-2">
              <ConfigBlock title={copy.conditions}>
                {selected.conditions.map((condition) => (
                  <CheckRow
                    key={condition}
                    checked={Boolean(conditions[condition])}
                    label={condition}
                    onChange={() => setConditions((prev) => ({ ...prev, [condition]: !prev[condition] }))}
                  />
                ))}
              </ConfigBlock>

              <ConfigBlock title={copy.actions}>
                {selected.actions.map((action) => (
                  <CheckRow
                    key={action.label}
                    checked={Boolean(actions[action.label])}
                    label={action.label}
                    badge={
                      action.risky
                        ? copy.statuses.risky
                        : action.recommended
                          ? copy.statuses.recommended
                          : undefined
                    }
                    badgeTone={action.risky ? 'warning' : 'neutral'}
                    onChange={() => setActions((prev) => ({ ...prev, [action.label]: !prev[action.label] }))}
                  />
                ))}
              </ConfigBlock>
            </div>
          </section>

          <StageScopePanel
            copy={copy.stages}
            ready={ready}
            workspaceId={workspaceId}
            connections={connections}
            selectedConnection={selectedConnection}
            selectedConnectionId={selectedConnectionId}
            connectionsLoading={connectionsLoading}
            connectionsError={connectionsError}
            exportOptions={visibleExportOptions}
            stagesLoading={stagesLoading}
            stagesError={stagesError}
            selectedStageIds={selectedStageIds}
            selectedStageNames={selectedStageNames}
            onConnectionChange={(connectionId) => {
              setSelectedConnectionId(connectionId || null);
              setSaved(false);
            }}
            onToggleStage={toggleStage}
            onTogglePipeline={togglePipeline}
            onSelectAll={selectAllCurrentStageScope}
            onClear={clearCurrentStageScope}
          />

          <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="card p-5">
              <h2 className="font-semibold">{copy.message}</h2>
              <textarea
                className="mt-3 min-h-32 w-full resize-y rounded-xl border border-border bg-white px-3 py-3 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                value={message}
                onChange={(event) => {
                  setMessage(event.target.value);
                  setSaved(false);
                }}
              />

              <div className="mt-5">
                <h3 className="text-sm font-semibold">{copy.risk}</h3>
                <div className="mt-3 grid gap-2 md:grid-cols-3">
                  {(['manager_approval', 'auto_draft', 'high_priority'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => {
                        setRiskMode(mode);
                        setSaved(false);
                      }}
                      className={cn(
                        'rounded-xl border p-3 text-left text-sm transition',
                        riskMode === mode ? 'border-primary bg-primary/10 text-foreground' : 'border-border bg-white text-muted-foreground hover:border-primary',
                      )}
                    >
                      {copy.riskModes[mode]}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <Button type="button" disabled={!canSaveRule} onClick={() => setSaved(true)}>
                  <CheckCircle2 className="h-4 w-4" />
                  {copy.save}
                </Button>
                <Button type="button" variant="secondary" onClick={resetCurrent}>
                  {copy.cancel}
                </Button>
              </div>
            </div>

            <div className="card p-5">
              <h2 className="font-semibold">{copy.selectedRule}</h2>
              <div className="mt-4 rounded-xl border border-border bg-muted/40 p-4 text-sm">
                <div className="font-semibold">{selected.title}</div>
                <div className="mt-3 space-y-2 text-muted-foreground">
                  <PreviewLine label={copy.conditions} value={`${selectedConditionsCount}/${selected.conditions.length}`} />
                  <PreviewLine label={copy.actions} value={`${selectedActionsCount}/${selected.actions.length}`} />
                  <PreviewLine
                    label={copy.stages.previewLabel}
                    value={selectedStageCount > 0 ? `${selectedStageCount}` : copy.stages.noneSelectedShort}
                  />
                  <PreviewLine label={copy.risk} value={copy.riskModes[riskMode]} />
                </div>
              </div>
              <div className="mt-4 rounded-xl border border-border bg-white p-4 text-sm">
                <div className="flex items-center gap-2 font-medium">
                  <MessageSquareText className="h-4 w-4 text-primary" />
                  {copy.message}
                </div>
                <p className="mt-2 leading-6 text-muted-foreground">{message || '—'}</p>
              </div>
              {saved ? (
                <div className="mt-4 rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-900">
                  <div className="font-semibold">{copy.savedTitle}</div>
                  <p className="mt-1 leading-5">{copy.savedBody}</p>
                </div>
              ) : null}
              {!saved && !canSaveRule ? (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                  {copy.stages.ruleDisabled}
                </div>
              ) : null}
            </div>
          </section>

          <section className="card border-amber-300 bg-amber-50 p-5">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
              <div>
                <h2 className="text-lg font-semibold text-foreground">{copy.safeTitle}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.safeBody}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-sm text-amber-900">
              <span className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1">
                <BellRing className="h-4 w-4" />
                Telegram/MAX
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1">
                <ArrowRight className="h-4 w-4" />
                amoCRM tasks later
              </span>
            </div>
          </section>
        </main>
      </section>
    </div>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-white/80 px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function StageScopePanel({
  copy,
  ready,
  workspaceId,
  connections,
  selectedConnection,
  selectedConnectionId,
  connectionsLoading,
  connectionsError,
  exportOptions,
  stagesLoading,
  stagesError,
  selectedStageIds,
  selectedStageNames,
  onConnectionChange,
  onToggleStage,
  onTogglePipeline,
  onSelectAll,
  onClear,
}: {
  copy: StageCopy;
  ready: boolean;
  workspaceId: string | null;
  connections: CrmConnection[];
  selectedConnection: CrmConnection | null;
  selectedConnectionId: string | null;
  connectionsLoading: boolean;
  connectionsError: string | null;
  exportOptions: ExportOptions | null;
  stagesLoading: boolean;
  stagesError: string | null;
  selectedStageIds: string[];
  selectedStageNames: string[];
  onConnectionChange: (connectionId: string) => void;
  onToggleStage: (stageId: string) => void;
  onTogglePipeline: (pipeline: ExportPipeline) => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  const [stageDropdownOpen, setStageDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const selectedSet = useMemo(() => new Set(selectedStageIds), [selectedStageIds]);
  const hasConnections = connections.length > 0;
  const hasPipelines = Boolean(exportOptions?.pipelines.length);
  const totalStageCount = useMemo(() => collectStageIds(exportOptions).length, [exportOptions]);

  useEffect(() => {
    if (!stageDropdownOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!dropdownRef.current?.contains(event.target as Node)) {
        setStageDropdownOpen(false);
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [stageDropdownOpen]);

  return (
    <section className="card">
      <div className="border-b border-border bg-muted/40 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold">{copy.title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{copy.subtitle}</p>
          </div>
          <Badge tone={selectedStageIds.length > 0 ? 'success' : 'warning'}>
            {copy.selected}: {selectedStageIds.length}
          </Badge>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
          <label className="block text-sm font-medium">
            {copy.connection}
            {connections.length > 1 ? (
              <div className="relative mt-2">
                <select
                  className="block w-full appearance-none rounded-xl border border-border bg-white px-3 py-3 pr-10 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                  value={selectedConnectionId ?? ''}
                  onChange={(event) => onConnectionChange(event.target.value)}
                >
                  {connections.map((connection) => (
                    <option key={connection.id} value={connection.id}>
                      {connectionLabel(connection)}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-3.5 h-4 w-4 text-muted-foreground" />
              </div>
            ) : (
              <div className="mt-2 rounded-xl border border-border bg-white px-3 py-3 text-sm text-foreground">
                {connectionsLoading
                  ? copy.loadingConnections
                  : selectedConnection
                    ? connectionLabel(selectedConnection)
                    : copy.noConnection}
              </div>
            )}
          </label>

          <div className="space-y-2">
            <div ref={dropdownRef} className="relative">
              <div className="text-sm font-medium">{copy.dropdownLabel}</div>
              <button
                type="button"
                className="mt-2 flex w-full items-center justify-between gap-3 rounded-xl border border-border bg-white px-3 py-3 text-left text-sm text-foreground transition hover:border-primary focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
                onClick={() => setStageDropdownOpen((open) => !open)}
                disabled={!hasPipelines || stagesLoading || Boolean(stagesError)}
              >
                <span className="min-w-0 flex-1 truncate">
                  {selectedStageIds.length
                    ? `${copy.selected}: ${selectedStageIds.length}/${totalStageCount}`
                    : copy.dropdownPlaceholder}
                </span>
                <ChevronDown
                  className={cn(
                    'h-4 w-4 shrink-0 text-muted-foreground transition',
                    stageDropdownOpen && 'rotate-180',
                  )}
                />
              </button>

              {stageDropdownOpen && exportOptions && hasPipelines ? (
                <div className="absolute left-0 right-0 z-30 mt-2 overflow-hidden rounded-2xl border border-border bg-white shadow-xl">
                  <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/40 p-3">
                    <button
                      type="button"
                      className="rounded-lg border border-border bg-white px-3 py-1.5 text-xs font-medium text-foreground hover:border-primary hover:text-primary"
                      onClick={onSelectAll}
                    >
                      {copy.selectAll}
                    </button>
                    <button
                      type="button"
                      className="rounded-lg border border-border bg-white px-3 py-1.5 text-xs font-medium text-muted-foreground hover:border-primary hover:text-primary"
                      onClick={onClear}
                    >
                      {copy.clearAll}
                    </button>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {selectedStageIds.length}/{totalStageCount}
                    </span>
                  </div>

                  <div className="max-h-96 overflow-y-auto p-2">
                    {exportOptions.pipelines.map((pipeline, pipelineIndex) => {
                      const stageIds = pipeline.stages.map((stage) => stage.id);
                      const allSelected = stageIds.length > 0 && stageIds.every((stageId) => selectedSet.has(stageId));
                      const someSelected = !allSelected && stageIds.some((stageId) => selectedSet.has(stageId));
                      return (
                        <div key={pipeline.id} className="rounded-xl p-2">
                          <label className="flex cursor-pointer items-center gap-3 rounded-lg bg-muted/50 px-3 py-2 text-left">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-primary"
                              checked={allSelected}
                              aria-checked={someSelected ? 'mixed' : allSelected}
                              disabled={!stageIds.length}
                              onChange={() => onTogglePipeline(pipeline)}
                            />
                            <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                              {pipelineIndex + 1}. {pipeline.name}
                            </span>
                            <Badge tone={someSelected || allSelected ? 'info' : 'neutral'}>
                              {allSelected ? copy.allPipelineStages : `${pipeline.stages.length}`}
                            </Badge>
                          </label>

                          <div className="mt-1 grid gap-1 pl-4">
                            {pipeline.stages.map((stage) => (
                              <label
                                key={stage.id}
                                className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm transition hover:bg-primary/5"
                              >
                                <input
                                  type="checkbox"
                                  className="h-4 w-4 accent-primary"
                                  checked={selectedSet.has(stage.id)}
                                  onChange={() => onToggleStage(stage.id)}
                                />
                                <span className="min-w-0 flex-1 truncate text-foreground">{stage.name}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-xl border border-border bg-white p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{copy.selectedChips}</span>
                {selectedStageNames.length ? (
                  selectedStageNames.slice(0, 6).map((name) => (
                    <Badge key={name} tone="neutral">
                      {name}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">{copy.noneSelected}</span>
                )}
                {selectedStageNames.length > 6 ? (
                  <Badge tone="neutral">+{selectedStageNames.length - 6}</Badge>
                ) : null}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{copy.visibleScopeHint}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="p-5">
        {!ready ? <StageState>{copy.loadingConnections}</StageState> : null}
        {ready && !workspaceId ? <StageState>{copy.noWorkspace}</StageState> : null}
        {ready && workspaceId && connectionsLoading ? <StageState>{copy.loadingConnections}</StageState> : null}
        {ready && workspaceId && connectionsError ? <StageState tone="danger">{connectionsError}</StageState> : null}
        {ready && workspaceId && !connectionsLoading && !hasConnections ? <StageState>{copy.noConnection}</StageState> : null}
        {selectedConnectionId && stagesLoading ? <StageState>{copy.loading}</StageState> : null}
        {selectedConnectionId && stagesError ? <StageState tone="danger">{stagesError}</StageState> : null}
        {selectedConnectionId && !stagesLoading && !stagesError && exportOptions && !hasPipelines ? (
          <StageState>{copy.empty}</StageState>
        ) : null}
      </div>
    </section>
  );
}

function StageState({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'danger' }) {
  return (
    <div
      className={cn(
        'rounded-xl border px-4 py-3 text-sm',
        tone === 'danger'
          ? 'border-red-200 bg-red-50 text-red-900'
          : 'border-border bg-muted/40 text-muted-foreground',
      )}
    >
      {children}
    </div>
  );
}

function ConfigBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-border p-5 lg:border-r last:lg:border-r-0">
      <h3 className="font-semibold">{title}</h3>
      <div className="mt-4 space-y-3">{children}</div>
    </div>
  );
}

function CheckRow({
  checked,
  label,
  badge,
  badgeTone = 'neutral',
  onChange,
}: {
  checked: boolean;
  label: string;
  badge?: string;
  badgeTone?: 'neutral' | 'warning';
  onChange: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-white p-3 transition hover:border-primary">
      <input className="mt-1 h-4 w-4 accent-primary" type="checkbox" checked={checked} onChange={onChange} />
      <span className="min-w-0 flex-1 text-sm leading-6 text-foreground">{label}</span>
      {badge ? <Badge tone={badgeTone}>{badge}</Badge> : null}
    </label>
  );
}

function PreviewLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>{label}</span>
      <strong className="text-right text-foreground">{value}</strong>
    </div>
  );
}

function normalizeExportOptions(options: ExportOptions): ExportOptions {
  return {
    ...options,
    active_pipeline_ids: (options.active_pipeline_ids ?? []).map((id) => String(id)),
    pipelines: (options.pipelines ?? []).map((pipeline) => ({
      ...pipeline,
      id: String(pipeline.id),
      stages: (pipeline.stages ?? []).map((stage) => ({
        id: String(stage.id),
        name: stage.name || String(stage.id),
        sort_order: stage.sort_order ?? null,
      })),
    })),
  };
}

function filterExportOptionsByActiveExport(
  options: ExportOptions | null,
  connection: CrmConnection | null,
): ExportOptions | null {
  if (!options) return null;
  const activePipelineIds = connection?.metadata?.active_export?.pipeline_ids ?? options.active_pipeline_ids ?? [];
  const allowedPipelineIds = activePipelineIds.map((id) => String(id).trim()).filter(Boolean);
  if (!allowedPipelineIds.length) return options;

  const allowed = new Set(allowedPipelineIds);
  return {
    ...options,
    active_pipeline_ids: allowedPipelineIds,
    pipelines: options.pipelines.filter((pipeline) => allowed.has(String(pipeline.id))),
  };
}

function collectStageIds(options: ExportOptions | null): string[] {
  if (!options) return [];
  return options.pipelines.flatMap((pipeline) => pipeline.stages.map((stage) => stage.id));
}

function restrictStageIds(stageIds: string[], allowedStageIds: string[]): string[] {
  if (!allowedStageIds.length) return [];
  const allowed = new Set(allowedStageIds);
  return stageIds.filter((stageId) => allowed.has(stageId));
}

function selectedStageLabels(options: ExportOptions | null, selectedStageIds: string[]): string[] {
  if (!options || selectedStageIds.length === 0) return [];
  const labels = new Map<string, string>();
  options.pipelines.forEach((pipeline) => {
    pipeline.stages.forEach((stage) => labels.set(stage.id, `${pipeline.name}: ${stage.name}`));
  });
  return selectedStageIds.map((stageId) => labels.get(stageId) ?? stageId);
}

function connectionLabel(connection: CrmConnection): string {
  const account = connection.metadata?.amo_account;
  const name = connection.name || account?.name || connection.external_domain || connection.external_account_id || connection.id;
  const domain = connection.external_domain || account?.subdomain;
  return domain && !String(name).includes(String(domain)) ? `${name} · ${domain}` : String(name);
}
