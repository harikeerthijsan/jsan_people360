import { api, apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { ApiResponse, MessageData } from '@/lib/api/types';
import type { LoginResult, PasswordResetIssued, Session, User } from '@/features/auth/types/auth.types';
import type {
  ChangePasswordFormValues,
  LoginPayload,
  ProfileFormValues,
  ResetPasswordFormValues,
} from '@/features/auth/schemas/auth.schemas';

/**
 * Transport layer for the auth feature.
 *
 * Only this module knows the endpoint shapes; hooks and components consume the
 * typed functions below.
 */
export const authApi = {
  login(payload: LoginPayload): Promise<LoginResult> {
    return api.post<LoginResult>(endpoints.auth.login, payload);
  },

  /**
   * Exchange the HttpOnly refresh cookie for a new session.
   *
   * `_skipAuthRefresh` stops the response interceptor from trying to recover a
   * 401 here: on first load an unauthenticated visitor *expects* this to fail,
   * and that must not be reported as an expired session.
   */
  refresh(): Promise<LoginResult> {
    return api.post<LoginResult>(endpoints.auth.refresh, {}, { _skipAuthRefresh: true });
  },

  async logout(allSessions = false): Promise<MessageData> {
    return api.post<MessageData>(endpoints.auth.logout, { all_sessions: allSessions });
  },

  /**
   * The signed-in caller's profile, roles and permissions.
   *
   * Login and refresh return the profile but not the permissions, so the
   * provider follows either of them with this call. One extra round trip buys a
   * single authority for what the session may do, rather than three payloads
   * that can disagree.
   */
  getSession(): Promise<Session> {
    return api.get<Session>(endpoints.auth.me);
  },

  updateProfile(payload: ProfileFormValues): Promise<User> {
    return api.patch<User>(endpoints.users.me, payload);
  },

  /**
   * Request a password reset.
   *
   * Returns the full envelope because the `message` is the user-facing result;
   * the endpoint deliberately succeeds whether or not the address is registered.
   */
  async forgotPassword(email: string): Promise<ApiResponse<PasswordResetIssued>> {
    const response = await apiClient.post<ApiResponse<PasswordResetIssued>>(endpoints.auth.forgotPassword, {
      email,
    });
    return response.data;
  },

  resetPassword(payload: ResetPasswordFormValues): Promise<MessageData> {
    return api.post<MessageData>(endpoints.auth.resetPassword, payload);
  },

  changePassword(payload: ChangePasswordFormValues): Promise<MessageData> {
    return api.post<MessageData>(endpoints.auth.changePassword, payload);
  },
};
