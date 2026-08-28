import { Award, Boxes, Building2, FileBadge, MapPin, Users2, type LucideIcon } from 'lucide-react';
import type { ZodType } from 'zod';

import type { DataTableColumn } from '@/components/common/data-table';
import { StatusBadge } from '@/components/common/status-badge';
import {
  SUPPORTED_CURRENCIES,
  SUPPORTED_TIMEZONES,
  businessUnitSchema,
  designationSchema,
  employmentTypeSchema,
  gradeSchema,
  locationSchema,
  organizationSchema,
  teamSchema,
} from '@/features/organization/schemas/organization.schemas';
import type {
  MasterFormValues,
  MasterRecord,
  MasterSlug,
} from '@/features/organization/types/organization.types';
import type { DetailItem } from '@/components/common/detail-view';

/**
 * The single declaration of every master.
 *
 * List columns, form fields, detail layout, validation and labels all come from
 * here, and the generic screens read it. Adding a tenth master is a new entry in
 * this file plus a nav link -- not another four pages of near-identical JSX.
 */

// ---------------------------------------------------------------------------
// Field configuration
// ---------------------------------------------------------------------------
export type MasterFieldType = 'text' | 'textarea' | 'number' | 'select' | 'reference';

export interface MasterFieldConfig {
  name: string;
  label: string;
  type: MasterFieldType;
  required?: boolean;
  placeholder?: string;
  description?: string;
  /** For `reference`: which master supplies the options. */
  referenceMaster?: MasterSlug;
  /** For `select`: the fixed option list. */
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
  rows?: number;
  /** Span both columns of the form grid. */
  wide?: boolean;
}

export interface MasterFieldGroup {
  title: string;
  description?: string;
  fields: MasterFieldConfig[];
}

export interface MasterConfig {
  slug: MasterSlug;
  label: string;
  labelPlural: string;
  icon: LucideIcon;
  /** One line explaining what the master is for, shown under the page title. */
  blurb: string;
  /** Zod schema validating the create/edit form. */
  schema: ZodType<MasterFormValues>;
  /** Blank form values, also used to reset the form. */
  emptyValues: MasterFormValues;
  /** Maps a record onto form values for the edit screen. */
  toFormValues: (record: MasterRecord) => MasterFormValues;
  /** Table columns, in display order. */
  columns: DataTableColumn<MasterRecord>[];
  /** Form layout. */
  groups: MasterFieldGroup[];
  /** Extra rows on the detail page, beyond the shared ones. */
  detailItems: (record: MasterRecord) => DetailItem[];
  /** Default sort column; must be one the API accepts. */
  defaultSortBy: string;
}

// ---------------------------------------------------------------------------
// Shared column and field builders
// ---------------------------------------------------------------------------
const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
];

const nameColumn: DataTableColumn<MasterRecord> = {
  id: 'name',
  header: 'Name',
  sortKey: 'name',
  cell: (row) => (
    <div className="min-w-0">
      <p className="text-foreground truncate font-medium">{row.name}</p>
      {row.description ? <p className="text-muted-foreground truncate text-xs">{row.description}</p> : null}
    </div>
  ),
};

const codeColumn: DataTableColumn<MasterRecord> = {
  id: 'code',
  header: 'Code',
  sortKey: 'code',
  className: 'w-36',
  cell: (row) => <span className="font-mono text-xs">{row.code ?? '—'}</span>,
};

const statusColumn: DataTableColumn<MasterRecord> = {
  id: 'status',
  header: 'Status',
  sortKey: 'status',
  align: 'right',
  className: 'w-32',
  cell: (row) => <StatusBadge status={row.status} archived={row.deleted_at !== null} />,
};

const levelColumn: DataTableColumn<MasterRecord> = {
  id: 'level',
  header: 'Level',
  sortKey: 'level',
  align: 'right',
  className: 'w-24',
  cell: (row) => <span className="tabular-nums">{row.level ?? '—'}</span>,
};

/** Renders an embedded parent summary, or a dash when absent. */
function parentCell(id: string, header: string, pick: (row: MasterRecord) => MasterRecord['business_unit']) {
  return {
    id,
    header,
    className: 'w-56',
    cell: (row: MasterRecord) => {
      const parent = pick(row);
      if (!parent) return <span className="text-muted-foreground">—</span>;
      return (
        <div className="min-w-0">
          <p className="truncate">{parent.name}</p>
          {parent.code ? (
            <p className="text-muted-foreground truncate font-mono text-xs">{parent.code}</p>
          ) : null}
        </div>
      );
    },
  } satisfies DataTableColumn<MasterRecord>;
}

const nameField: MasterFieldConfig = {
  name: 'name',
  label: 'Name',
  type: 'text',
  required: true,
  placeholder: 'e.g. Technology Services',
};

const codeField: MasterFieldConfig = {
  name: 'code',
  label: 'Code',
  type: 'text',
  required: true,
  placeholder: 'e.g. TECH',
  description: 'Short stable identifier. Upper-cased automatically.',
};

const statusField: MasterFieldConfig = {
  name: 'status',
  label: 'Status',
  type: 'select',
  required: true,
  options: STATUS_OPTIONS,
  description: 'Inactive records stay referenceable but are hidden from new selections.',
};

const descriptionField: MasterFieldConfig = {
  name: 'description',
  label: 'Description',
  type: 'textarea',
  wide: true,
  placeholder: 'What is this used for?',
};

const timezoneOptions = SUPPORTED_TIMEZONES.map((zone) => ({ value: zone, label: zone }));
const currencyOptions = SUPPORTED_CURRENCIES.map((code) => ({ value: code, label: code }));

/** Base form values shared by every master. */
const baseValues: MasterFormValues = { name: '', description: '', status: 'active' };
const codedValues: MasterFormValues = { ...baseValues, code: '' };

/** Pull the shared fields off a record for the edit form. */
function baseFormValues(record: MasterRecord): MasterFormValues {
  return {
    name: record.name,
    description: record.description ?? '',
    status: record.status,
  };
}

function codedFormValues(record: MasterRecord): MasterFormValues {
  return { ...baseFormValues(record), code: record.code ?? '' };
}

// ---------------------------------------------------------------------------
// The registry
// ---------------------------------------------------------------------------
export const MASTER_REGISTRY: Record<MasterSlug, MasterConfig> = {
  'business-units': {
    slug: 'business-units',
    label: 'Business unit',
    labelPlural: 'Business units',
    icon: Building2,
    blurb: 'The top level of the organizational hierarchy. Teams and designations belong to a business unit.',
    schema: businessUnitSchema,
    emptyValues: codedValues,
    toFormValues: codedFormValues,
    columns: [nameColumn, codeColumn, statusColumn],
    groups: [{ title: 'Details', fields: [nameField, codeField, statusField, descriptionField] }],
    detailItems: () => [],
    defaultSortBy: 'name',
  },

  teams: {
    slug: 'teams',
    label: 'Team',
    labelPlural: 'Teams',
    icon: Users2,
    blurb: 'Teams within a business unit. Managers reference user accounts until the Employee module exists.',
    schema: teamSchema,
    emptyValues: { ...baseValues, business_unit_id: '', manager_id: '' },
    toFormValues: (record) => ({
      ...baseFormValues(record),
      business_unit_id: record.business_unit_id ?? '',
      manager_id: record.manager_id ?? '',
    }),
    columns: [
      nameColumn,
      parentCell('business_unit', 'Business unit', (row) => row.business_unit),
      {
        id: 'manager',
        header: 'Manager',
        className: 'w-48',
        cell: (row) =>
          row.manager ? (
            <span className="truncate">{row.manager.full_name}</span>
          ) : (
            <span className="text-muted-foreground">Unassigned</span>
          ),
      },
      statusColumn,
    ],
    groups: [
      {
        title: 'Details',
        fields: [
          nameField,
          {
            name: 'business_unit_id',
            label: 'Business unit',
            type: 'reference',
            required: true,
            referenceMaster: 'business-units',
          },
          statusField,
          descriptionField,
        ],
      },
    ],
    detailItems: (record) => [
      { label: 'Business unit', value: record.business_unit?.name ?? null },
      { label: 'Manager', value: record.manager?.full_name ?? null },
    ],
    defaultSortBy: 'name',
  },

  designations: {
    slug: 'designations',
    label: 'Designation',
    labelPlural: 'Designations',
    icon: FileBadge,
    blurb: 'Job titles within a business unit, ordered by seniority level.',
    schema: designationSchema,
    emptyValues: { ...codedValues, business_unit_id: '', level: undefined },
    toFormValues: (record) => ({
      ...codedFormValues(record),
      business_unit_id: record.business_unit_id ?? '',
      level: record.level,
    }),
    columns: [
      nameColumn,
      codeColumn,
      parentCell('business_unit', 'Business unit', (row) => row.business_unit),
      levelColumn,
      statusColumn,
    ],
    groups: [
      {
        title: 'Details',
        fields: [
          nameField,
          codeField,
          {
            name: 'business_unit_id',
            label: 'Business unit',
            type: 'reference',
            required: true,
            referenceMaster: 'business-units',
          },
          {
            name: 'level',
            label: 'Seniority level',
            type: 'number',
            required: true,
            min: 1,
            max: 99,
            description: '1 is the most junior. Used for ordering only.',
          },
          statusField,
          descriptionField,
        ],
      },
    ],
    detailItems: (record) => [
      { label: 'Business unit', value: record.business_unit?.name ?? null },
      { label: 'Seniority level', value: record.level ?? null },
    ],
    defaultSortBy: 'level',
  },

  locations: {
    slug: 'locations',
    label: 'Location',
    labelPlural: 'Locations',
    icon: MapPin,
    blurb: 'Offices and work sites. Attendance and scheduling resolve against a location time zone.',
    schema: locationSchema,
    emptyValues: {
      ...codedValues,
      country: '',
      state: '',
      city: '',
      address: '',
      timezone: 'Asia/Kolkata',
    },
    toFormValues: (record) => ({
      ...codedFormValues(record),
      country: record.country ?? '',
      state: record.state ?? '',
      city: record.city ?? '',
      address: record.address ?? '',
      timezone: record.timezone ?? '',
    }),
    columns: [
      nameColumn,
      codeColumn,
      {
        id: 'place',
        header: 'City',
        sortKey: 'city',
        className: 'w-48',
        cell: (row) => (
          <div className="min-w-0">
            <p className="truncate">{row.city ?? '—'}</p>
            <p className="text-muted-foreground truncate text-xs">{row.country ?? ''}</p>
          </div>
        ),
      },
      {
        id: 'timezone',
        header: 'Time zone',
        className: 'w-40',
        cell: (row) => <span className="text-xs">{row.timezone ?? '—'}</span>,
      },
      statusColumn,
    ],
    groups: [
      {
        title: 'Details',
        fields: [nameField, codeField, statusField, descriptionField],
      },
      {
        title: 'Address',
        fields: [
          { name: 'country', label: 'Country', type: 'text', required: true, placeholder: 'India' },
          { name: 'state', label: 'State', type: 'text', required: true, placeholder: 'Telangana' },
          { name: 'city', label: 'City', type: 'text', required: true, placeholder: 'Hyderabad' },
          {
            name: 'timezone',
            label: 'Time zone',
            type: 'select',
            required: true,
            options: timezoneOptions,
          },
          {
            name: 'address',
            label: 'Full address',
            type: 'textarea',
            required: true,
            wide: true,
            rows: 3,
          },
        ],
      },
    ],
    detailItems: (record) => [
      { label: 'City', value: record.city ?? null },
      { label: 'State', value: record.state ?? null },
      { label: 'Country', value: record.country ?? null },
      { label: 'Time zone', value: record.timezone ?? null },
      { label: 'Address', value: record.address ?? null, wide: true },
    ],
    defaultSortBy: 'name',
  },

  'employment-types': {
    slug: 'employment-types',
    label: 'Employment type',
    labelPlural: 'Employment types',
    icon: Boxes,
    blurb: 'How a person is engaged: full time, contract, intern and so on.',
    schema: employmentTypeSchema,
    emptyValues: codedValues,
    toFormValues: codedFormValues,
    columns: [nameColumn, codeColumn, statusColumn],
    groups: [{ title: 'Details', fields: [nameField, codeField, statusField, descriptionField] }],
    detailItems: () => [],
    defaultSortBy: 'name',
  },

  grades: {
    slug: 'grades',
    label: 'Grade',
    labelPlural: 'Grades',
    icon: Award,
    blurb: 'Compensation and seniority bands such as G1, G2 or M1.',
    schema: gradeSchema,
    emptyValues: { ...codedValues, level: undefined },
    toFormValues: (record) => ({ ...codedFormValues(record), level: record.level }),
    columns: [nameColumn, codeColumn, levelColumn, statusColumn],
    groups: [
      {
        title: 'Details',
        fields: [
          nameField,
          codeField,
          {
            name: 'level',
            label: 'Level',
            type: 'number',
            required: true,
            min: 1,
            max: 99,
            description: '1 is the most junior. Used for ordering only.',
          },
          statusField,
          descriptionField,
        ],
      },
    ],
    detailItems: (record) => [{ label: 'Level', value: record.level ?? null }],
    defaultSortBy: 'level',
  },

  organizations: {
    slug: 'organizations',
    label: 'Organization',
    labelPlural: 'Organizations',
    icon: Building2,
    blurb: 'The legal entity the platform is operated for, with its registration and address.',
    schema: organizationSchema,
    emptyValues: {
      ...baseValues,
      legal_name: '',
      registration_number: '',
      gst_number: '',
      pan_number: '',
      website: '',
      logo_url: '',
      timezone: 'Asia/Kolkata',
      currency: 'INR',
      address_line1: '',
      address_line2: '',
      city: '',
      state: '',
      country: '',
      postal_code: '',
    },
    toFormValues: (record) => ({
      ...baseFormValues(record),
      legal_name: record.legal_name ?? '',
      registration_number: record.registration_number ?? '',
      gst_number: record.gst_number ?? '',
      pan_number: record.pan_number ?? '',
      website: record.website ?? '',
      logo_url: record.logo_url ?? '',
      timezone: record.timezone ?? '',
      currency: record.currency ?? '',
      address_line1: record.address_line1 ?? '',
      address_line2: record.address_line2 ?? '',
      city: record.city ?? '',
      state: record.state ?? '',
      country: record.country ?? '',
      postal_code: record.postal_code ?? '',
    }),
    columns: [
      {
        id: 'name',
        header: 'Company',
        sortKey: 'name',
        cell: (row) => (
          <div className="min-w-0">
            <p className="text-foreground truncate font-medium">{row.name}</p>
            <p className="text-muted-foreground truncate text-xs">{row.legal_name ?? ''}</p>
          </div>
        ),
      },
      {
        id: 'registration_number',
        header: 'Registration',
        className: 'w-56',
        cell: (row) => <span className="font-mono text-xs">{row.registration_number ?? '—'}</span>,
      },
      {
        id: 'city',
        header: 'City',
        sortKey: 'city',
        className: 'w-40',
        cell: (row) => row.city ?? '—',
      },
      statusColumn,
    ],
    groups: [
      {
        title: 'Company',
        fields: [
          { ...nameField, label: 'Company name', placeholder: 'e.g. JSAN Technologies' },
          {
            name: 'legal_name',
            label: 'Legal name',
            type: 'text',
            required: true,
            placeholder: 'e.g. JSAN Technologies Private Limited',
          },
          {
            name: 'registration_number',
            label: 'Registration number',
            type: 'text',
            required: true,
          },
          statusField,
          descriptionField,
        ],
      },
      {
        title: 'Tax identifiers',
        description: 'Both are optional and validated for shape only.',
        fields: [
          { name: 'gst_number', label: 'GST number', type: 'text', placeholder: '36AABCJ1234M1ZP' },
          { name: 'pan_number', label: 'PAN', type: 'text', placeholder: 'ABCDE1234F' },
        ],
      },
      {
        title: 'Presentation and locale',
        fields: [
          { name: 'website', label: 'Website', type: 'text', placeholder: 'https://example.com' },
          { name: 'logo_url', label: 'Logo URL', type: 'text', placeholder: 'https://example.com/logo.png' },
          {
            name: 'timezone',
            label: 'Time zone',
            type: 'select',
            required: true,
            options: timezoneOptions,
          },
          {
            name: 'currency',
            label: 'Currency',
            type: 'select',
            required: true,
            options: currencyOptions,
          },
        ],
      },
      {
        title: 'Registered address',
        fields: [
          { name: 'address_line1', label: 'Address line 1', type: 'text', required: true, wide: true },
          { name: 'address_line2', label: 'Address line 2', type: 'text', wide: true },
          { name: 'city', label: 'City', type: 'text', required: true },
          { name: 'state', label: 'State', type: 'text', required: true },
          { name: 'country', label: 'Country', type: 'text', required: true },
          { name: 'postal_code', label: 'Postal code', type: 'text' },
        ],
      },
    ],
    detailItems: (record) => [
      { label: 'Legal name', value: record.legal_name ?? null },
      { label: 'Registration number', value: record.registration_number ?? null },
      { label: 'GST number', value: record.gst_number ?? null },
      { label: 'PAN', value: record.pan_number ?? null },
      { label: 'Website', value: record.website ?? null },
      { label: 'Time zone', value: record.timezone ?? null },
      { label: 'Currency', value: record.currency ?? null },
      {
        label: 'Registered address',
        wide: true,
        value: [
          record.address_line1,
          record.address_line2,
          record.city,
          record.state,
          record.country,
          record.postal_code,
        ]
          .filter((part): part is string => Boolean(part))
          .join(', '),
      },
    ],
    defaultSortBy: 'name',
  },
};

/** Slugs in the order they appear in the sidebar and on the overview page. */
export const MASTER_ORDER: MasterSlug[] = [
  'organizations',
  'business-units',
  'teams',
  'designations',
  'locations',
  'employment-types',
  'grades',
];

/** Look up a master by slug, or `undefined` for an unknown one. */
export function getMasterConfig(slug: string): MasterConfig | undefined {
  return Object.hasOwn(MASTER_REGISTRY, slug) ? MASTER_REGISTRY[slug as MasterSlug] : undefined;
}
