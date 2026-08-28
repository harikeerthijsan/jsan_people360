'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useRouter } from 'next/navigation';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { ErrorState } from '@/components/common/error-state';
import { FormActions, FormLayout, FormSection } from '@/components/common/form-layout';
import { FormSkeleton } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Form } from '@/components/ui/form';
import { MASTER_REGISTRY, type MasterConfig } from '@/features/organization/config/master-registry';
import { MasterFormField } from '@/features/organization/components/master-form-field';
import { useCreateMaster, useMasterRecord, useUpdateMaster } from '@/features/organization/hooks/use-masters';
import type { MasterFormValues, MasterSlug } from '@/features/organization/types/organization.types';

interface MasterFormPageProps {
  /** See the note on `MasterListPageProps.slug`. */
  slug: MasterSlug;
  /** Omit to create; supply to edit. */
  recordId?: string;
}

/**
 * The create and edit screen for every master.
 *
 * One component covers both because the only differences are the initial values,
 * which mutation runs and where it navigates afterwards.
 */
export function MasterFormPage({ slug, recordId }: MasterFormPageProps): React.JSX.Element {
  const config: MasterConfig = MASTER_REGISTRY[slug];
  const router = useRouter();
  const isEdit = recordId !== undefined;
  const basePath = `/organization/${config.slug}`;

  const recordQuery = useMasterRecord(config.slug, recordId);
  const createMutation = useCreateMaster(config.slug, config.label);
  const updateMutation = useUpdateMaster(config.slug, config.label);

  const form = useForm<MasterFormValues>({
    resolver: zodResolver(config.schema),
    defaultValues: config.emptyValues,
    mode: 'onSubmit',
  });

  // Populate the form once the record arrives. `reset` also re-baselines the
  // dirty state, so an untouched edit form correctly reports "nothing changed".
  const { reset } = form;
  const record = recordQuery.data;
  React.useEffect(() => {
    if (record) {
      reset(config.toFormValues(record));
    }
  }, [config, record, reset]);

  const mutation = isEdit ? updateMutation : createMutation;

  const onSubmit = form.handleSubmit((values) => {
    const onError = (error: { fieldErrorMap: Record<string, string> }) => {
      // Field-scoped API errors (a duplicate name or code) attach to their
      // input; anything else falls through to the alert above the form.
      for (const [field, message] of Object.entries(error.fieldErrorMap)) {
        form.setError(field, { type: 'server', message });
      }
    };

    if (isEdit) {
      updateMutation.mutate(
        { id: recordId, values },
        {
          onSuccess: (updated) => {
            router.push(`${basePath}/${updated.id}`);
          },
          onError,
        },
      );
      return;
    }

    createMutation.mutate(values, {
      onSuccess: (created) => {
        router.push(`${basePath}/${created.id}`);
      },
      onError,
    });
  });

  if (isEdit && recordQuery.isPending) {
    return (
      <div className="space-y-6">
        <PageHeader title={`Edit ${config.label.toLowerCase()}`} />
        <FormSkeleton fields={5} />
      </div>
    );
  }

  if (isEdit && recordQuery.isError) {
    return (
      <div className="space-y-6">
        <PageHeader title={`Edit ${config.label.toLowerCase()}`} />
        <ErrorState
          error={recordQuery.error}
          onRetry={() => {
            void recordQuery.refetch();
          }}
        />
      </div>
    );
  }

  const isArchived = record?.deleted_at !== null && record?.deleted_at !== undefined;

  // A duplicate name or code is reported per field; anything else is general.
  const generalError =
    mutation.error && Object.keys(mutation.error.fieldErrorMap).length === 0 ? mutation.error.message : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={isEdit ? `Edit ${config.label.toLowerCase()}` : `New ${config.label.toLowerCase()}`}
        description={config.blurb}
      />

      {isArchived ? (
        <Alert variant="warning">
          <AlertDescription>
            This {config.label.toLowerCase()} is archived and cannot be edited. Restore it first.
          </AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <FormLayout onSubmit={onSubmit}>
          {generalError ? (
            <Alert variant="destructive">
              <AlertDescription>{generalError}</AlertDescription>
            </Alert>
          ) : null}

          {config.groups.map((group) => (
            <FormSection key={group.title} title={group.title} description={group.description}>
              {group.fields.map((field) => (
                <MasterFormField
                  key={field.name}
                  field={field}
                  control={form.control}
                  disabled={mutation.isPending || isArchived}
                />
              ))}
            </FormSection>
          ))}

          <FormActions
            submitLabel={isEdit ? 'Save changes' : `Create ${config.label.toLowerCase()}`}
            isSubmitting={mutation.isPending}
            // On create the form starts pristine but is still submittable;
            // on edit there is nothing to save until something changes.
            isDirty={!isArchived && (!isEdit || form.formState.isDirty)}
            cancelHref={isEdit && recordId ? `${basePath}/${recordId}` : basePath}
          />
        </FormLayout>
      </Form>
    </div>
  );
}
