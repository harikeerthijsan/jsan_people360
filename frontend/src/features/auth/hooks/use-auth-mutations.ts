'use client';

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { useAuth } from '@/components/providers/auth-provider';
import { authApi } from '@/features/auth/api/auth.api';
import type {
  ChangePasswordFormValues,
  LoginPayload,
  ProfileFormValues,
  ResetPasswordFormValues,
} from '@/features/auth/schemas/auth.schemas';
import type { PasswordResetIssued, User } from '@/features/auth/types/auth.types';
import type { ApiResponse, MessageData } from '@/lib/api/types';
import { type AppError } from '@/lib/errors';
import { queryKeys } from '@/lib/query-client';

/** Sign in and establish the session. */
export function useLogin(): UseMutationResult<User, AppError, LoginPayload> {
  const { login } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<User, AppError, LoginPayload>({
    mutationFn: (payload) => login(payload),
    onSuccess: (user) => {
      // Seed the cache so the shell renders immediately without a second fetch.
      queryClient.setQueryData(queryKeys.auth.currentUser(), user);
    },
  });
}

/** Request a password reset link. */
export function useForgotPassword(): UseMutationResult<ApiResponse<PasswordResetIssued>, AppError, string> {
  return useMutation<ApiResponse<PasswordResetIssued>, AppError, string>({
    mutationFn: (email) => authApi.forgotPassword(email),
  });
}

/** Complete a password reset with a token from the emailed link. */
export function useResetPassword(): UseMutationResult<MessageData, AppError, ResetPasswordFormValues> {
  return useMutation<MessageData, AppError, ResetPasswordFormValues>({
    mutationFn: (payload) => authApi.resetPassword(payload),
  });
}

/** Change the password of the signed-in user. */
export function useChangePassword(): UseMutationResult<MessageData, AppError, ChangePasswordFormValues> {
  return useMutation<MessageData, AppError, ChangePasswordFormValues>({
    mutationFn: (payload) => authApi.changePassword(payload),
  });
}

/** Update the signed-in user's own profile. */
export function useUpdateProfile(): UseMutationResult<User, AppError, ProfileFormValues> {
  const { setUser } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<User, AppError, ProfileFormValues>({
    mutationFn: (payload) => authApi.updateProfile(payload),
    onSuccess: (user) => {
      setUser(user);
      queryClient.setQueryData(queryKeys.auth.currentUser(), user);
    },
  });
}
