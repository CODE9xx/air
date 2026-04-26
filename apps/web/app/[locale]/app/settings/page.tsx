'use client';

import { FormEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useUserAuth } from '@/components/providers/AuthProvider';
import { api, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useToast } from '@/components/ui/Toast';

export default function CabinetSettingsPage() {
  const t = useTranslations('cabinet.settings');
  const { user, setUser } = useUserAuth();
  const { toast } = useToast();
  const [newEmail, setNewEmail] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestEmailChange = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.post('/auth/email-change/request', {
        new_email: newEmail,
        current_password: currentPassword,
      });
      setCodeSent(true);
      toast({ kind: 'success', title: 'Код отправлен', description: 'Проверьте новую почту и введите код подтверждения.' });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Не удалось отправить код';
      setError(message);
      toast({ kind: 'error', title: 'Смена почты', description: message });
    } finally {
      setLoading(false);
    }
  };

  const confirmEmailChange = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await api.post<{ ok: boolean; email: string }>('/auth/email-change/confirm', { code });
      const me = await api.get<typeof user>('/auth/me');
      setUser(me);
      setNewEmail('');
      setCurrentPassword('');
      setCode('');
      setCodeSent(false);
      toast({ kind: 'success', title: 'Почта изменена', description: result.email });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Не удалось подтвердить код';
      setError(message);
      toast({ kind: 'error', title: 'Смена почты', description: message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
      <div className="card p-6 space-y-4">
        <h2 className="font-semibold">{t('profile')}</h2>
        <Field label={t('email')} value={user?.email ?? '—'} />
        <Field label={t('displayName')} value={user?.display_name ?? '—'} />
        <Field label={t('locale')} value={user?.locale ?? 'ru'} />
      </div>
      <div className="card p-6 space-y-4">
        <div>
          <h2 className="font-semibold">Смена e-mail</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Код подтверждения отправляется на новую почту. Пароль нужен, чтобы защитить аккаунт от случайной смены.
          </p>
        </div>
        {!codeSent ? (
          <form className="space-y-3" onSubmit={requestEmailChange}>
            <label className="block text-sm font-medium">
              Новая почта
              <Input
                className="mt-1"
                type="email"
                value={newEmail}
                onChange={(event) => setNewEmail(event.target.value)}
                placeholder="name@example.com"
                required
              />
            </label>
            <label className="block text-sm font-medium">
              Текущий пароль
              <Input
                className="mt-1"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </label>
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            <Button type="submit" loading={loading}>Отправить код</Button>
          </form>
        ) : (
          <form className="space-y-3" onSubmit={confirmEmailChange}>
            <label className="block text-sm font-medium">
              Код из письма
              <Input
                className="mt-1"
                inputMode="numeric"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="000000"
                maxLength={6}
                required
              />
            </label>
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" loading={loading}>Подтвердить смену</Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setCodeSent(false);
                  setCode('');
                  setError(null);
                }}
              >
                Изменить почту
              </Button>
            </div>
          </form>
        )}
      </div>
      <div className="card p-6 space-y-4">
        <h2 className="font-semibold">{t('workspace')}</h2>
        <Field label={t('workspaceName')} value={user?.workspaces?.[0]?.name ?? '—'} />
      </div>
      <div className="card p-6 border border-danger bg-red-50">
        <h2 className="font-semibold text-danger">{t('dangerZone')}</h2>
        <p className="text-sm text-muted-foreground mt-2">{t('deleteAccount')}</p>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}
