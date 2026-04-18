// Преобразование ApiError в i18n-ключ auth.errors.*
import { ApiError } from '@/lib/api';

export function mapAuthErrorKey(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case 'invalid_credentials':
        return 'auth.errors.invalidCredentials';
      case 'email_not_verified':
        return 'auth.errors.emailNotVerified';
      case 'conflict':
        return 'auth.errors.emailTaken';
      case 'code_expired':
        return 'auth.errors.codeExpired';
      case 'too_many_attempts':
        return 'auth.errors.tooManyAttempts';
      case 'rate_limited':
        return 'auth.errors.rateLimited';
      default:
        return 'auth.errors.generic';
    }
  }
  return 'auth.errors.generic';
}
