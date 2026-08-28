'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Form } from '@/components/ui/form';
import { Label } from '@/components/ui/label';
import { useCreateLeaveType, useLeaveTypes, useUpdateLeaveType } from '@/features/workforce/hooks';
import { leaveTypeSchema, type LeaveTypeFormValues } from '@/features/workforce/schema';
import type { LeaveType } from '@/features/workforce/types';

const BLANK: LeaveTypeFormValues = {
  name: '',
  code: '',
  description: '',
  annual_allocation: '0',
  carry_forward: false,
  max_carry_forward: '0',
  allows_negative: false,
  is_paid: true,
  requires_document: false,
  status: 'active',
};

/** The three flags that change what a leave type means, as one labelled group. */
function FlagRow({
  checked,
  description,
  id,
  label,
  onChange,
}: {
  checked: boolean;
  description: string;
  id: string;
  label: string;
  onChange: (value: boolean) => void;
}): React.JSX.Element {
  return (
    <div className="flex items-start gap-3">
      <Checkbox
        checked={checked}
        id={id}
        onCheckedChange={(value) => {
          onChange(value === true);
        }}
      />
      <div className="space-y-0.5">
        <Label htmlFor={id}>{label}</Label>
        <p className="text-muted-foreground text-sm">{description}</p>
      </div>
    </div>
  );
}

/**
 * Leave types.
 *
 * The statutory Indian set ships with the system, so this screen exists to add
 * what a company runs on top of it rather than to build the list from nothing.
 * A type is deactivated rather than deleted: leave already taken under it has
 * to stay readable.
 */
export function LeaveTypesPage(): React.JSX.Element {
  const [editing, setEditing] = React.useState<LeaveType | null>(null);
  const [isOpen, setIsOpen] = React.useState(false);

  const query = useLeaveTypes();
  const create = useCreateLeaveType();
  const update = useUpdateLeaveType(editing?.id ?? '');

  const form = useForm<LeaveTypeFormValues>({
    resolver: zodResolver(leaveTypeSchema),
    defaultValues: BLANK,
  });

  const open = (leaveType: LeaveType | null): void => {
    setEditing(leaveType);
    form.reset(
      leaveType
        ? {
            name: leaveType.name,
            code: leaveType.code,
            description: leaveType.description ?? '',
            annual_allocation: leaveType.annual_allocation,
            carry_forward: leaveType.carry_forward,
            max_carry_forward: leaveType.max_carry_forward,
            allows_negative: leaveType.allows_negative,
            is_paid: leaveType.is_paid,
            requires_document: leaveType.requires_document,
            status: leaveType.status,
          }
        : BLANK,
    );
    setIsOpen(true);
  };

  const submit = form.handleSubmit((values) => {
    const mutation = editing ? update : create;
    mutation.mutate(values, {
      onSuccess: () => {
        setIsOpen(false);
        setEditing(null);
      },
    });
  });

  const columns: DataTableColumn<LeaveType>[] = [
    {
      id: 'name',
      header: 'Type',
      cell: (row) => (
        <div>
          <span className="font-medium">{row.name}</span>
          <span className="text-muted-foreground ml-2 text-sm">{row.code}</span>
        </div>
      ),
    },
    {
      id: 'allocation',
      header: 'Days a year',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.annual_allocation}</span>,
    },
    {
      id: 'carry',
      header: 'Carry forward',
      cell: (row) => (row.carry_forward ? `Up to ${row.max_carry_forward}` : 'No'),
    },
    {
      id: 'flags',
      header: 'Rules',
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          <Badge variant={row.is_paid ? 'secondary' : 'outline'}>{row.is_paid ? 'Paid' : 'Unpaid'}</Badge>
          {row.requires_document ? <Badge variant="outline">Document required</Badge> : null}
          {row.allows_negative ? <Badge variant="warning">Can go negative</Badge> : null}
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'active' ? 'success' : 'outline'}>
          {row.status === 'active' ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button
          onClick={() => {
            open(row);
          }}
          size="sm"
          variant="outline"
        >
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leave types"
        description="What can be applied for, how much of it, and what carries into next year."
        actions={
          <Button
            onClick={() => {
              open(null);
            }}
          >
            Add leave type
          </Button>
        }
      />

      <DataTable
        columns={columns}
        emptyDescription="No leave types are configured."
        emptyTitle="Nothing configured"
        error={query.error}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        onRetry={() => void query.refetch()}
        rows={query.data ?? []}
      />

      <Modal
        onOpenChange={setIsOpen}
        open={isOpen}
        size="lg"
        title={editing ? `Edit ${editing.name}` : 'Add a leave type'}
        description="Changing an allocation affects balances created from now on, not ones already issued."
        footer={
          <>
            <Button
              onClick={() => {
                setIsOpen(false);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button isLoading={create.isPending || update.isPending} onClick={() => void submit()}>
              Save
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submit(event)}>
            <FormSection title="Identity">
              <TextField control={form.control} label="Name" name="name" required />
              <TextField
                control={form.control}
                description="Short code used in reports, e.g. CL."
                label="Code"
                name="code"
                required
              />
              <TextareaField
                className="sm:col-span-2"
                control={form.control}
                label="Description"
                name="description"
                rows={2}
              />
            </FormSection>

            <FormSection title="Entitlement">
              <TextField
                control={form.control}
                description="Days credited at the start of the year. Zero means it is granted case by case."
                label="Annual allocation"
                name="annual_allocation"
                required
              />
              <TextField
                control={form.control}
                description="Only meaningful when carry forward is on."
                label="Maximum carry forward"
                name="max_carry_forward"
              />
              <SelectField
                control={form.control}
                label="Status"
                name="status"
                options={[
                  { value: 'active', label: 'Active' },
                  { value: 'inactive', label: 'Inactive', hint: 'Cannot be chosen for new requests' },
                ]}
                required
              />
            </FormSection>

            <FormSection columns={1} title="Rules">
              <FlagRow
                checked={form.watch('carry_forward')}
                description="Unused days move into next year, up to the maximum above."
                id="carry-forward"
                label="Carries forward"
                onChange={(value) => {
                  form.setValue('carry_forward', value, { shouldDirty: true });
                }}
              />
              <FlagRow
                checked={form.watch('is_paid')}
                description="Unpaid types still consume a balance; they simply are not paid."
                id="is-paid"
                label="Paid leave"
                onChange={(value) => {
                  form.setValue('is_paid', value, { shouldDirty: true });
                }}
              />
              <FlagRow
                checked={form.watch('requires_document')}
                description="A supporting document is expected, such as a medical certificate."
                id="requires-document"
                label="Needs a document"
                onChange={(value) => {
                  form.setValue('requires_document', value, { shouldDirty: true });
                }}
              />
              <FlagRow
                checked={form.watch('allows_negative')}
                description="Applications are allowed past the balance, leaving it negative."
                id="allows-negative"
                label="Can go negative"
                onChange={(value) => {
                  form.setValue('allows_negative', value, { shouldDirty: true });
                }}
              />
            </FormSection>
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
