import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LoginForm } from '@/features/auth/components/login-form';
import { AppError } from '@/lib/errors';

// ---------------------------------------------------------------------------
// Test doubles
// ---------------------------------------------------------------------------
const replace = jest.fn();
const searchParams = new URLSearchParams();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: jest.fn(), refresh: jest.fn() }),
  useSearchParams: () => searchParams,
  usePathname: () => '/login',
}));

const login = jest.fn();

jest.mock('@/components/providers/auth-provider', () => ({
  useAuth: () => ({
    user: null,
    status: 'unauthenticated',
    isAuthenticated: false,
    login,
    logout: jest.fn(),
    setUser: jest.fn(),
  }),
}));

function renderLoginForm() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <LoginForm />
    </QueryClientProvider>,
  );
}

describe('LoginForm', () => {
  beforeEach(() => {
    replace.mockReset();
    login.mockReset();
  });

  it('renders the credential fields and submit button', () => {
    renderLoginForm();

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('shows validation errors and does not call the API for an invalid email', async () => {
    renderLoginForm();

    await userEvent.type(screen.getByLabelText(/email address/i), 'not-an-email');
    await userEvent.type(screen.getByLabelText(/^password/i), 'Some@Password1');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it('requires a password', async () => {
    renderLoginForm();

    await userEvent.type(screen.getByLabelText(/email address/i), 'admin@example.com');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/password is required/i)).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it('submits normalised credentials and redirects on success', async () => {
    login.mockResolvedValue({ id: 'user-1', email: 'admin@example.com' });
    renderLoginForm();

    await userEvent.type(screen.getByLabelText(/email address/i), '  Admin@Example.COM ');
    await userEvent.type(screen.getByLabelText(/^password/i), 'Admin@12345');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith({
        email: 'admin@example.com',
        password: 'Admin@12345',
        remember_me: false,
      });
    });

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith('/dashboard');
    });
  });

  it('surfaces a rejected sign-in as an alert', async () => {
    login.mockRejectedValue(
      new AppError('Incorrect email or password.', { status: 401, code: 'invalid_credentials' }),
    );
    renderLoginForm();

    await userEvent.type(screen.getByLabelText(/email address/i), 'admin@example.com');
    await userEvent.type(screen.getByLabelText(/^password/i), 'Wrong@Password1');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.');
    expect(replace).not.toHaveBeenCalled();
  });

  it('toggles password visibility', async () => {
    renderLoginForm();

    const passwordInput = screen.getByLabelText(/^password/i);
    expect(passwordInput).toHaveAttribute('type', 'password');

    await userEvent.click(screen.getByRole('button', { name: /show password/i }));

    expect(passwordInput).toHaveAttribute('type', 'text');
  });
});
