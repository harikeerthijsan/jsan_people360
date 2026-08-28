'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useRouter, useSearchParams } from 'next/navigation';
import * as React from 'react';
import { useForm, type DefaultValues, type FieldValues, type Resolver } from 'react-hook-form';

import { FileUpload } from '@/components/common/file-upload';
import { FormActions, FormLayout, FormSection } from '@/components/common/form-layout';
import { PageHeader } from '@/components/common/page-header';
import { SelectField, type SelectOption } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Form } from '@/components/ui/form';
import {
  useDocumentCategories,
  useDocumentTypes,
  useUploadDocument,
} from '@/features/documents/hooks/use-documents';
import { useOwnerOptions } from '@/features/documents/hooks/use-owner-options';
import { uploadDocumentSchema, validateFile } from '@/features/documents/schemas/document.schemas';
import {
  ACCEPTED_EXTENSIONS,
  MAX_UPLOAD_MB,
  OWNER_TYPE_LABELS,
  type DocumentOwnerType,
} from '@/features/documents/types/document.types';

const BASE_PATH = '/documents';

const OWNER_TYPE_OPTIONS: SelectOption[] = (Object.keys(OWNER_TYPE_LABELS) as DocumentOwnerType[]).map(
  (type) => ({ value: type, label: OWNER_TYPE_LABELS[type] }),
);

/**
 * The picker for whoever the document belongs to.
 *
 * Which list to load depends on the owner type, so every query is declared and
 * only the relevant one is enabled — hooks cannot be called conditionally, and
 * branching before the call would break the rules of hooks.
 *
 * Candidates are here because onboarding sends people straight to this form
 * with `?owner_type=candidate`. Leaving them out made that link a dead end: the
 * owner type rendered blank and the picker could never be filled in.
 */
function OwnerField({
  control,
  ownerType,
  disabled,
}: {
  control: ReturnType<typeof useForm<FieldValues>>['control'];
  ownerType: DocumentOwnerType | undefined;
  disabled: boolean;
}): React.JSX.Element {
  const owners = useOwnerOptions(ownerType);

  return (
    <SelectField
      control={control}
      name="owner_id"
      label="Belongs to"
      options={owners.options}
      isLoading={owners.isLoading}
      emptyMessage={owners.emptyMessage}
      required
      disabled={disabled || ownerType === undefined}
    />
  );
}

export function DocumentUploadPage(): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const upload = useUploadDocument();

  const [file, setFile] = React.useState<File | null>(null);
  const [fileError, setFileError] = React.useState<string | null>(null);

  // Pre-filled when arriving from an employee's document panel, so the person
  // who sent you here does not have to be looked up again.
  const defaults: FieldValues = React.useMemo(
    () => ({
      name: '',
      category_id: '',
      document_type_id: '',
      owner_type: searchParams.get('owner_type') ?? 'employee',
      owner_id: searchParams.get('owner_id') ?? '',
      description: '',
      expiry_date: '',
    }),
    [searchParams],
  );

  const form = useForm<FieldValues>({
    resolver: zodResolver(uploadDocumentSchema) as Resolver<FieldValues>,
    defaultValues: defaults as DefaultValues<FieldValues>,
    mode: 'onSubmit',
  });

  const ownerType = form.watch('owner_type') as DocumentOwnerType | undefined;
  const categoryId = form.watch('category_id') as string | undefined;

  const categories = useDocumentCategories();
  const types = useDocumentTypes(categoryId || undefined);

  const categoryOptions: SelectOption[] = (categories.data?.items ?? []).map((item) => ({
    value: item.id,
    label: item.name,
    hint: item.code,
  }));

  const typeOptions: SelectOption[] = (types.data?.items ?? []).map((item) => ({
    value: item.id,
    label: item.name,
    hint: item.requires_expiry ? 'Expiry required' : item.code,
  }));

  const submit = form.handleSubmit((values) => {
    if (!file) {
      setFileError('Choose a file to upload.');
      return;
    }

    upload.mutate(
      {
        file,
        fields: {
          name: String(values['name']),
          category_id: String(values['category_id']),
          document_type_id: String(values['document_type_id']),
          owner_type: String(values['owner_type']),
          owner_id: String(values['owner_id']),
          description: values['description'] as string | null,
          expiry_date: values['expiry_date'] as string | null,
        },
      },
      {
        onSuccess: (document) => {
          router.push(`${BASE_PATH}/${document.id}`);
        },
      },
    );
  });

  React.useEffect(() => {
    if (!upload.error) return;
    for (const [field, message] of Object.entries(upload.error.fieldErrorMap)) {
      form.setError(field, { type: 'server', message });
    }
  }, [upload.error, form]);

  const generalError =
    upload.error && Object.keys(upload.error.fieldErrorMap).length === 0 ? upload.error.message : null;

  const disabled = upload.isPending;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Upload document"
        description="Files are checked against their actual content, not just the file name."
      />

      <Form {...form}>
        <FormLayout onSubmit={submit}>
          {generalError ? (
            <Alert variant="destructive">
              <AlertDescription>{generalError}</AlertDescription>
            </Alert>
          ) : null}

          <FormSection title="File" description={`Accepted: ${ACCEPTED_EXTENSIONS.join(', ')}.`}>
            <div className="sm:col-span-2">
              <FileUpload
                onSelect={(selected) => {
                  setFile(selected);
                  setFileError(null);
                }}
                validate={validateFile}
                accept={ACCEPTED_EXTENSIONS.join(',')}
                progress={upload.progress}
                isUploading={upload.isPending}
                disabled={disabled}
                hint={`Up to ${String(MAX_UPLOAD_MB)} MB`}
              />
              {fileError ? (
                <p role="alert" className="text-destructive mt-2 text-sm">
                  {fileError}
                </p>
              ) : null}
            </div>
          </FormSection>

          <FormSection title="Classification" description="How this document is filed.">
            <SelectField
              control={form.control}
              name="category_id"
              label="Category"
              options={categoryOptions}
              isLoading={categories.isPending}
              emptyMessage="No active categories. Add one under Documents settings."
              required
              disabled={disabled}
            />
            <SelectField
              control={form.control}
              name="document_type_id"
              label="Document type"
              options={typeOptions}
              isLoading={Boolean(categoryId) && types.isPending}
              emptyMessage={categoryId ? 'No active types in this category' : 'Choose a category first'}
              required
              disabled={disabled || !categoryId}
            />
          </FormSection>

          <FormSection title="Owner" description="What this document belongs to.">
            <SelectField
              control={form.control}
              name="owner_type"
              label="Owner type"
              options={OWNER_TYPE_OPTIONS}
              required
              disabled={disabled}
            />
            <OwnerField control={form.control} ownerType={ownerType} disabled={disabled} />
          </FormSection>

          <FormSection title="Details">
            <TextField
              control={form.control}
              name="name"
              label="Document name"
              description="What a person would call it — 'Passport', not the file name."
              required
              disabled={disabled}
            />
            <TextField
              control={form.control}
              name="expiry_date"
              label="Expiry date"
              type="date"
              description="Required for some types, such as a passport."
              disabled={disabled}
            />
            <TextareaField
              control={form.control}
              name="description"
              label="Description"
              rows={3}
              className="sm:col-span-2"
              disabled={disabled}
            />
          </FormSection>

          <FormActions
            submitLabel="Upload document"
            isSubmitting={upload.isPending}
            isDirty
            cancelHref={BASE_PATH}
          />
        </FormLayout>
      </Form>
    </div>
  );
}
