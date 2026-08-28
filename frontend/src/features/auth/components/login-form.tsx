'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { TextField } from '@/components/common/text-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem, FormLabel } from '@/components/ui/form';
import { routes } from '@/config/site';
import { useLogin } from '@/features/auth/hooks/use-auth-mutations';
import { loginSchema, type LoginFormValues } from '@/features/auth/schemas/auth.schemas';

/** Credentials form for the sign-in page. */
export function LoginForm(): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '', remember_me: false },
    mode: 'onSubmit',
  });

  const onSubmit = form.handleSubmit((values) => {
    login.mutate(values, {
      onSuccess: () => {
        // Return the user to wherever they were headed before the redirect.
        const next = searchParams.get('next');
        router.replace(next && next.startsWith('/') ? next : routes.dashboard);
      },
      onError: (error) => {
        // Field-scoped messages from the API attach to their inputs; anything
        // else falls through to the alert above the form.
        for (const [field, message] of Object.entries(error.fieldErrorMap)) {
          if (field === 'email' || field === 'password') {
            form.setError(field, { type: 'server', message });
          }
        }
      },
    });
  });

  const generalError =
    login.error && Object.keys(login.error.fieldErrorMap).length === 0 ? login.error.message : null;

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {generalError ? (
          <Alert variant="destructive">
            <AlertDescription>{generalError}</AlertDescription>
          </Alert>
        ) : null}

        <TextField
          control={form.control}
          name="email"
          label="Email address"
          type="email"
          placeholder="you@company.com"
          autoComplete="email"
          required
          disabled={login.isPending}
        />

        <TextField
          control={form.control}
          name="password"
          label="Password"
          type="password"
          placeholder="Enter your password"
          autoComplete="current-password"
          required
          disabled={login.isPending}
        />

        <div className="flex items-center justify-between">
          <FormField
            control={form.control}
            name="remember_me"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center gap-2 space-y-0">
                <FormControl>
                  <Checkbox
                    checked={field.value ?? false}
                    onCheckedChange={(checked) => {
                      field.onChange(checked === true);
                    }}
                    disabled={login.isPending}
                  />
                </FormControl>
                <FormLabel className="text-muted-foreground cursor-pointer text-sm font-normal">
                  Keep me signed in
                </FormLabel>
              </FormItem>
            )}
          />

          <Link
            href={routes.forgotPassword}
            className="text-primary hover:text-primary-hover text-sm font-medium transition-colors hover:underline"
          >
            Forgot password?
          </Link>
        </div>

        <Button type="submit" className="w-full" size="lg" isLoading={login.isPending}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </Form>
  );
}
