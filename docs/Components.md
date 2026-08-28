# Reusable components

The shared component library. Everything here is designed to be used by future
HR modules without modification. Phase 1 established it; Phases 2 and 3 added
`StatusBadge`, `Pagination`, `SearchBar`, `DetailSection`, the form fields, and
the four people-shaped components in [People](#people); Phase 4 added
`EmploymentStatusBadge`, `EmployeeCard`, `MaskedValue`, `Tabs` and `Timeline`.

Two tiers:

- **`src/components/ui/`** — Shadcn/Radix primitives. Generic, no product
  knowledge. Replaceable.
- **`src/components/common/`** — composed, product-level components that encode
  how *this* product behaves.

Feature code should reach for `common/` first and drop to `ui/` only when
composing something new.

---

## Design tokens

All colour, radius, typography and layout values are declared once in
`src/app/globals.css`. Components reference semantic tokens (`bg-primary`),
never raw palette values (`bg-blue-600`), so the product can be rethemed from a
single file.

| Token group | Tokens |
| --- | --- |
| Surfaces | `background`, `foreground`, `card`, `popover` |
| Brand | `primary`, `primary-foreground`, `primary-hover`, `primary-subtle` |
| Neutrals | `secondary`, `muted`, `muted-foreground`, `accent` |
| Status | `destructive`, `success`, `warning` (each with `-foreground` and `-subtle`) |
| Lines | `border`, `input`, `ring` |
| Shape | `--radius` (0.5rem) with `sm`/`md`/`lg`/`xl` derivatives |
| Layout | `--sidebar-width`, `--header-height` |

Dark-mode values are already defined under `.dark`. Phase 1 ships light only; a
theme toggle later is a provider change, not a restyle.

---

## UI primitives (`components/ui/`)

| Component | Exports | Notes |
| --- | --- | --- |
| `alert` | `Alert`, `AlertTitle`, `AlertDescription` | Variants: `default`, `info`, `success`, `warning`, `destructive`. Carries `role="alert"` |
| `avatar` | `Avatar`, `AvatarImage`, `AvatarFallback` | Falls back to initials |
| `badge` | `Badge` | Variants: `default`, `secondary`, `success`, `warning`, `destructive`, `outline` |
| `button` | `Button`, `buttonVariants` | Variants: `default`, `destructive`, `outline`, `secondary`, `ghost`, `link`. Sizes: `sm`, `default`, `lg`, `icon` |
| `card` | `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter` | The standard content container |
| `checkbox` | `Checkbox` | Radix-backed, keyboard accessible |
| `dialog` | `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogFooter`, `DialogTrigger`, `DialogClose` | Focus trap and scroll lock included |
| `dropdown-menu` | `DropdownMenu`, `…Trigger`, `…Content`, `…Item`, `…Label`, `…Separator`, `…CheckboxItem`, `…Sub*` | `Item` supports `variant="destructive"` |
| `form` | `Form`, `FormField`, `FormItem`, `FormLabel`, `FormControl`, `FormDescription`, `FormMessage`, `useFormField` | React Hook Form bindings; wires `aria-describedby` and `aria-invalid` |
| `input` | `Input` | Error styling driven by `aria-invalid` |
| `label` | `Label` | Optional `required` renders the asterisk |
| `separator` | `Separator` | Horizontal or vertical |
| `sheet` | `Sheet`, `SheetContent`, `SheetTitle`, `SheetDescription`, `SheetTrigger`, `SheetClose` | Edge-anchored dialog; used for mobile navigation |
| `skeleton` | `Skeleton` | `aria-hidden`; the container announces the busy state |
| `sonner` | `Toaster`, `toast` | Toast host, styled from the design tokens |
| `table` | `Table`, `TableHeader`, `TableBody`, `TableFooter`, `TableRow`, `TableHead`, `TableCell`, `TableCaption` | Wrapper scrolls horizontally rather than breaking page layout |
| `tooltip` | `TooltipProvider`, `Tooltip`, `TooltipTrigger`, `TooltipContent` | Provider is mounted globally |

### `Button` — note on `isLoading`

`isLoading` also sets `disabled` and `aria-busy`, so a submitting button cannot
be left clickable by mistake.

```tsx
<Button isLoading={mutation.isPending}>Save changes</Button>
```

---

## Product components (`components/common/`)

### `PageHeader`

The title block at the top of every screen.

```tsx
<PageHeader
  title="Employees"
  description="Everyone currently on the payroll."
  actions={<Button>Add employee</Button>}
/>
```

### `StatCard`

A KPI tile. The trend arrow and its colour are derived from the sign of `trend`.

```tsx
<StatCard label="Total employees" value={248} hint="vs. last month" trend={4.2} icon={Users} />
```

### `DataTable`

**The table for every list screen.** It owns all four display states, so feature
screens never reimplement them and can never render an empty table body while a
request is still in flight.

```tsx
const columns: DataTableColumn<Employee>[] = [
  { id: 'name', header: 'Name', cell: (row) => row.fullName },
  { id: 'department', header: 'Department', cell: (row) => row.department },
  { id: 'salary', header: 'Salary', align: 'right', cell: (row) => formatCurrency(row.salary) },
];

<DataTable
  columns={columns}
  rows={query.data ?? []}
  getRowId={(row) => row.id}
  isLoading={query.isPending}
  error={query.error}
  onRetry={() => void query.refetch()}
  onRowClick={(row) => router.push(`/employees/${row.id}`)}
  emptyTitle="No employees yet"
  emptyDescription="Add your first employee to get started."
/>
```

| Prop | Purpose |
| --- | --- |
| `columns` | Column definitions — id, header, cell renderer, alignment, `sortKey` |
| `rows` / `getRowId` | Data and stable identity |
| `isLoading` | Renders a column-matched skeleton |
| `error` / `onRetry` | Renders the error state; takes precedence over rows |
| `onRowClick` | Makes rows keyboard-operable **only** when supplied |
| `emptyTitle` / `emptyDescription` / `emptyAction` | Empty-state copy and its call to action |
| `sort` / `onSortChange` | Turns headers with a `sortKey` into sort controls |

Sorting is server-side: a column's `sortKey` is sent to the API, and the active
header carries `aria-sort` so the current order is announced rather than only
shown as an icon.

### `EmptyState`

Explains an absence *and* offers the next step.

```tsx
<EmptyState
  icon={Users}
  title="No employees yet"
  description="Add your first employee to get started."
  action={{ label: 'Add employee', onClick: openCreateModal }}
/>
```

### `ErrorState`

Renders any thrown value. The message always comes from `AppError`, which is
populated from the backend's user-facing `message`; stack traces never reach it.
Network failures get their own icon and copy.

```tsx
<ErrorState error={query.error} onRetry={() => void query.refetch()} />
```

### Loading states

| Export | Use for |
| --- | --- |
| `Spinner` | Inline, next to text |
| `LoadingState` | A whole region with a message |
| `StatCardSkeleton` | A KPI tile |
| `TableSkeleton` | A table — pass `columns` to match |
| `FormSkeleton` | A form panel — pass `fields` |

Prefer a skeleton over a spinner whenever the shape of the incoming content is
known; it avoids the layout shift a spinner causes when real content lands.

### `Modal` and `ConfirmDialog`

```tsx
<Modal
  open={disclosure.isOpen}
  onOpenChange={disclosure.setOpen}
  title="Add employee"
  description="Create a new employee record."
  size="lg"
  confirmLabel="Create"
  onConfirm={handleCreate}
  isConfirming={mutation.isPending}
>
  <EmployeeForm />
</Modal>

<ConfirmDialog
  open={confirm.isOpen}
  onOpenChange={confirm.setOpen}
  title="Delete this employee?"
  description="Their records will be archived and removed from active lists."
  confirmLabel="Delete"
  destructive
  onConfirm={handleDelete}
/>
```

Sizes: `sm` | `md` | `lg` | `xl`. Supplying `footer` replaces the default
Cancel/Confirm pair.

### `SearchBar`

Debounced search input. Locally controlled so typing stays responsive; the
committed value is reported only after the user pauses. Without the debounce,
every keystroke fires a request and results flicker as stale responses arrive out
of order. Clearing (button or `Escape`) bypasses the debounce.

```tsx
<SearchBar value={state.search} onChange={state.setSearch} placeholder="Search teams…" />
```

### `StatusBadge`

Renders a master record's state as one badge.

```tsx
<StatusBadge status={record.status} archived={record.deleted_at !== null} />
```

Archived deliberately takes precedence over, and is labelled distinctly from,
inactive — they are different states, and collapsing them would hide that.

### `Pagination`

Page controls plus a plain-language range summary ("Showing 21–40 of 57
teams"). The summary matters as much as the buttons: bare arrows do not tell
the user where they are. Renders nothing when there are no results.

```tsx
<Pagination meta={page.meta} onPageChange={state.setPage} itemLabel="teams" />
```

### `FormSection`, `FormActions`, `FormLayout`

The form skeleton. `FormSection` is a titled, optionally two-column group of
fields; `FormActions` is the Cancel/Save pair, laid out identically everywhere.
Cancel is a link, not a button, so middle-click and "open in new tab" behave as
expected.

```tsx
<Form {...form}>
  <FormLayout onSubmit={onSubmit}>
    <FormSection title="Details">{/* fields */}</FormSection>
    <FormActions submitLabel="Save changes" isSubmitting={mutation.isPending} cancelHref="/organization/grades" />
  </FormLayout>
</Form>
```

### `DetailSection`

Labelled read-only fields, rendered as a real `<dl>` so the label/value
relationship reaches assistive technology rather than only being implied by
layout. Empty values render an em dash instead of collapsing, which keeps the
grid aligned and makes "not set" visible rather than ambiguous.

```tsx
<DetailSection title="Details" items={[{ label: 'Code', value: record.code }]} />
```

### `SelectField`, `TextareaField`, `NumberField`

React Hook Form-bound inputs, matching `TextField` below.

`SelectField` handles the states a naive select forgets — options still loading,
and no options at all — because an empty dropdown leaves the user unable to tell
whether data is missing or merely slow.

`NumberField` converts the native input's string value to a real `number` (and
`""` to `undefined`), so Zod's `number()` does not reject a valid entry.

```tsx
<SelectField control={form.control} name="business_unit_id" label="Business unit"
             options={options} isLoading={query.isPending} required />
```

### `TextField`

**The field every form should use.** It wires the label, description, error
message and ARIA attributes together, so a screen declares only intent.
`type="password"` additionally gets a show/hide toggle.

```tsx
<TextField
  control={form.control}
  name="email"
  label="Email address"
  type="email"
  placeholder="you@company.com"
  autoComplete="email"
  description="We'll never share this."
  required
  disabled={mutation.isPending}
/>
```

---

## People

Four components added by the User Management module. They are in `common/`
rather than inside the feature because every later HR module — employees,
recruitment, approvals — displays a person.

### `UserAvatar`

Photo, falling back to initials.

```tsx
<UserAvatar name={user.full_name} photoUrl={user.avatar_url} size="lg" />
```

Sizes: `sm` | `md` | `lg` | `xl`. The image `alt` is deliberately empty — the
name is always rendered beside the avatar or supplied by the surrounding
control, so describing the image again would make a screen reader announce it
twice.

### `UserIdentity`

Avatar plus name and a secondary line: the pairing every user row and picker
needs, as a single table cell.

```tsx
<UserIdentity name={row.full_name} secondary={row.email} photoUrl={row.avatar_url} />
```

Both text lines truncate, so a long name cannot push a table column out of shape.

### `ProfileCard`

The banner at the top of a person's page.

```tsx
<ProfileCard
  name={user.full_name}
  subtitle={user.email}
  photoUrl={user.avatar_url}
  badges={<StatusBadge status={user.status} archived={user.deleted_at !== null} />}
  facts={[{ label: 'Business unit', value: user.organization.business_unit?.name ?? '—' }]}
  actions={<Button>Edit</Button>}
/>
```

Kept separate from `DetailSection` because it is a summary, not a field list: it
leads with identity, so the reader knows whose record they are looking at before
any of the detail below.

### `ActionMenu`

The row-level actions dropdown, declared as **data rather than JSX**.

```tsx
<ActionMenu
  label={`Actions for ${row.full_name}`}
  items={[
    { id: 'edit', label: 'Edit', icon: Pencil, href: `/users/${row.id}/edit`, hidden: isArchived },
    { id: 'deactivate', label: 'Deactivate', icon: MinusCircle,
      separatorBefore: true, disabled: isSelf, onSelect: () => deactivate.mutate(row.id) },
    { id: 'archive', label: 'Archive', icon: Trash2, destructive: true, onSelect: confirmArchive },
  ]}
/>
```

| Item property | Effect |
| --- | --- |
| `href` | Renders as a link instead of a button — middle-click and "open in new tab" work |
| `hidden` | Removed entirely |
| `disabled` | Shown but not selectable |
| `destructive` | Destructive styling |
| `separatorBefore` | Draws a divider above |

Taking a list is what lets a screen compute which actions apply to each row
without rebuilding the same menu. Prefer `hidden` over `disabled` when the action
makes no sense in the current state — offering "Restore" on a live record is
noise, not a hint.

`label` becomes the trigger's accessible name, so every row's menu is
distinguishable. The trigger stops click propagation, so opening the menu does
not also navigate the row.

### `EmploymentStatusBadge`

An employee's lifecycle status as one badge.

```tsx
<EmploymentStatusBadge status={employee.employment_status} archived={employee.deleted_at !== null} />
```

Separate from `StatusBadge`, which renders the master-data active/inactive pair.
Six states with different meanings do not collapse into two, and pretending they
do is how "on notice" ends up looking identical to "resigned". Archived takes
precedence: a hidden record's lifecycle state is moot.

### `EmployeeCard`

A person as a compact card — photo, name, employee ID, placement, status. For
where a table row would be too dense to scan: a manager's direct reports, a
picker's results, a dashboard list.

```tsx
<EmployeeCard employee={employee} href={`/employees/${employee.id}`} actions={<ActionMenu … />} />
```

---

## Documents

Built for the vault, but deliberately generic: recruitment, onboarding and
offboarding will each need a document panel, and none of them should write their
own uploader.

### `FileUpload`

A drag-and-drop picker with an upload progress bar.

```tsx
<FileUpload
  onSelect={setFile}
  validate={validateFile}                    // returns { message } or null
  accept={ACCEPTED_EXTENSIONS.join(',')}
  isUploading={upload.isPending}
  progress={upload.progress}
  hint="PDF, JPG or PNG, up to 10 MB"
/>
```

A real `<input type="file">` inside a label, with the drop zone layered over it —
not a div with a click handler, which no keyboard reaches and no screen reader
announces. Dragging over a child fires `dragleave` on the parent, so the
highlight is driven by an enter/leave *counter* rather than a boolean that would
flicker as the pointer crosses the icon.

Validation is injected. The component knows how to accept a file and show a
problem; what counts as a problem belongs to the caller. Rejections carry
`role="alert"` because someone mid-drag is not looking at this corner of the
screen. Clearing resets the input's value, without which the same file cannot be
picked twice — no change event would fire.

### `ImageViewer`, `PdfViewer`, `FilePreviewModal`

Viewers for the formats the vault accepts, and the modal that hosts them.

```tsx
<FilePreviewModal
  open={isOpen}
  onOpenChange={setIsOpen}
  title={document.name}
  description={`Version ${version.version_number}`}
  filename={version.original_filename}
  contentType={version.content_type}
  url={preview.url}                          // object URL, null while fetching
  isLoading={preview.isLoading}
  onDownload={handleDownload}
/>
```

All three take an **object URL, never an API path**. The file endpoints require a
bearer token, so the bytes are fetched by the application and handed over already
in memory; pointing an `<img>` at the API would send an unauthenticated request
and render a broken image. `PdfViewer` uses `<object>` rather than `<iframe>` so
a browser with no PDF plugin falls back to a download button instead of a blank
rectangle.

### `DocumentStatusBadge`, `ExpiryBadge`

Review status and expiry, as two badges.

```tsx
<DocumentStatusBadge status={document.status} archived={document.deleted_at !== null} />
<ExpiryBadge state={document.expiry_state} detail={formatDate(document.expiry_date)} />
```

Two rather than one, because they answer different questions — a document can be
approved *and* expired, and collapsing them hides whichever the reader needed.
Archived takes precedence over status, as with `EmploymentStatusBadge`.
`ExpiryBadge` renders **nothing** for a document that does not expire: a "No
expiry" chip on every résumé would be noise that makes the real warnings harder
to spot.

### `DocumentCard`

A document as a compact card — name, code, type, status, expiry, current file.

```tsx
<DocumentCard document={document} href={`/documents/${document.id}`} actions={<ActionMenu … />} />
```

For where a table row would be too dense to scan: an employee's document panel, a
candidate's application, a dashboard's "needs attention" list. Version 1 is the
norm and so is not labelled; anything above it is.

### `VersionTimeline`

A document's version history (`features/documents/`).

```tsx
<VersionTimeline
  versions={versions.data ?? []}
  currentVersionId={document.current_version?.id ?? null}
  onPreview={openPreview}
  onDownload={download}
/>
```

Built on the shared `Timeline`. What is specific is that every entry stays
actionable: an older version is not an archive note, it is a file someone may
still need to open, so each row keeps its own preview and download.

---

## Sensitive values

### `MaskedValue`

A sensitive value with an explicit reveal.

```tsx
<MaskedValue
  label="Aadhaar number"
  masked={identification.aadhaar_number}      // what the server sent
  revealed={sensitive.data?.aadhaar_number}   // fetched only on request
  isRevealed={revealed}
  isLoading={sensitive.isFetching}
  onToggle={() => setRevealed((previous) => !previous)}
/>
```

The masked form is **what the server sent** — never derived on the client, which
would mean the full value was in the page all along. The unmasked form arrives
only when the reader asks, and asking is audited. That is why revealing is a
button rather than a hover: a hover is something a mouse does, not something a
person decides.

The toggle carries `aria-pressed` and an accessible name that names the field, so
a screen-reader user knows which value they are uncovering.

---

## Structure

### `Tabs`

Tabs whose selection lives in the URL.

```tsx
<Tabs tabs={TABS} label="Employee profile sections" defaultTabId="overview">
  {(activeTab) => <ProfileTab tab={activeTab} employee={employee} />}
</Tabs>
```

Built here rather than pulled in as another Radix primitive, because the
behaviour that matters is the URL binding: a colleague can be sent "look at the
bank tab of this employee" as a link, the back button steps between tabs, and a
refresh stays where you were. An unknown tab in the URL falls back to the default
rather than rendering nothing.

Keyboard behaviour follows the WAI-ARIA tabs pattern — arrow keys move between
tabs, Home and End jump to the ends — using a roving tabindex, so only the active
tab is in the tab order.

The strip scrolls rather than wrapping: eight tabs on a phone would otherwise
become three rows and push the content off the screen.

### `Timeline`

A vertical timeline of dated events.

```tsx
<Timeline
  items={[
    {
      id: entry.id,
      title: 'Promoted',
      timestamp: formatDate(entry.effective_date),
      description: entry.summary,
      meta: <p>Reason: {entry.reason}</p>,
      highlighted: true,
    },
  ]}
/>
```

Generic on purpose: the employment history and the audit trail both render
through it, and onboarding checklists and approval chains have the same shape. It
knows about a rail, a marker and an ordered list — nothing about employees.

Rendered as a real `<ol>`, because the sequence *is* the content and a stack of
divs would leave a screen reader with no way to convey it. The rail stops at the
last marker rather than trailing into nothing, which would read as "more below".
`highlighted` emphasises the entries a reader scans for — a promotion among a run
of detail edits.

---

## Layout components (`components/layout/`)

| Component | Purpose |
| --- | --- |
| `AppShell` | The authenticated frame: sidebar, header, content. Also guards the subtree (a usability guard — the API enforces authorisation) |
| `AuthShell` | Split layout for sign-in and password recovery; bounces authenticated visitors to the dashboard |
| `Sidebar` | Permanent desktop navigation (`lg` and up) |
| `MobileNav` | The same navigation in a drawer below `lg` |
| `SidebarNav` | The grouped nav itself, shared by both |
| `Header` | Sticky header: menu trigger, breadcrumbs, environment badge, account menu |
| `Breadcrumbs` | Derived from the route; labels come from the navigation config so the two cannot drift |
| `UserMenu` | Profile links, sign out, sign out everywhere |
| `Brand` | Product lockup, with a `compact` variant |

---

## Hooks

| Hook | Returns |
| --- | --- |
| `useAuth()` | `{ user, status, isAuthenticated, login, logout, setUser }` |
| `useBreadcrumbs()` | `Breadcrumb[]` for the current route |
| `useDisclosure(initial?)` | `{ isOpen, open, close, toggle, setOpen }` |
| `useMediaQuery(query)` | `boolean`, via `useSyncExternalStore` |
| `useIsDesktop()` | `boolean` — matches the Tailwind `lg` breakpoint |

---

## A standard list screen

Putting the pieces together:

```tsx
'use client';

export default function EmployeesPage() {
  const createModal = useDisclosure();
  const employees = useEmployees();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employees"
        description="Everyone currently on the payroll."
        actions={<Button onClick={createModal.open}>Add employee</Button>}
      />

      <DataTable
        columns={columns}
        rows={employees.data ?? []}
        getRowId={(row) => row.id}
        isLoading={employees.isPending}
        error={employees.error}
        onRetry={() => void employees.refetch()}
        emptyTitle="No employees yet"
        emptyDescription="Add your first employee to get started."
      />

      <Modal
        open={createModal.isOpen}
        onOpenChange={createModal.setOpen}
        title="Add employee"
        size="lg"
      >
        <EmployeeForm onSuccess={createModal.close} />
      </Modal>
    </div>
  );
}
```

---

## Accessibility

Behaviour that is already handled, and should not be re-implemented per screen:

- **Focus.** One `:focus-visible` treatment defined globally.
- **Skip link.** The root layout provides "Skip to main content".
- **Forms.** `TextField` wires `aria-invalid` and `aria-describedby`;
  `FormMessage` carries `role="alert"`.
- **Errors and alerts.** `Alert` and `ErrorState` use `role="alert"`.
- **Loading.** Loading regions use `role="status"` with `aria-live="polite"`;
  decorative skeletons are `aria-hidden`.
- **Navigation.** `aria-current="page"` on the active item; breadcrumbs are an
  ordered list inside a labelled `nav`.
- **Interactive rows.** `DataTable` rows get `tabIndex`, `role="button"` and
  Enter/Space handling *only* when `onRowClick` is supplied — non-interactive
  rows stay out of the tab order.
- **Reduced motion.** `prefers-reduced-motion` is respected globally.
- **Icons.** Decorative icons are `aria-hidden`; icon-only buttons have
  `aria-label`.

---

## Adding a component

1. Generic and reusable across any product? → `components/ui/`.
2. Encodes how *this* product behaves? → `components/common/`.
3. Only one feature will ever use it? → `features/<module>/components/`.

Every component should: accept `className` and merge it with `cn()`, use
semantic tokens rather than raw colours, be typed without `any`, handle its own
loading and error states if it fetches, and be keyboard-operable.

## Workforce widgets

`src/components/common/workforce-widgets.tsx` holds the pieces the workforce
screens share. They are in one file because they are small and always used
together: an attendance row carries a status badge and a worked-hours figure, a
leave row carries an approval badge, and the calendar reuses both.

| Export | Does |
| --- | --- |
| `AttendanceStatusBadge` | Present, absent, half day, on leave, holiday, weekly off |
| `ApprovalStatusBadge` | Pending, approved, rejected, cancelled |
| `TimesheetStatusBadge` | Draft, submitted, approved, rejected |
| `WorkModeBadge` | Office, remote, hybrid, client site |
| `formatMinutes` | `465` → `"7h 45m"` |
| `ShiftSummary` | A shift as one line: name, type, window, grace |
| `LeaveBalanceCard` | Entitlement with held days shown apart from spent ones |
| `AttendanceCalendar` | A month grid, colour-coded, with a legend |

`formatMinutes` renders hours and minutes rather than a decimal because a
decimal invites the reader to mistake `7.45` for seven hours forty-five.

`LeaveBalanceCard` shows held days separately from spent ones. They behave
differently — held days come back if the request is rejected — and a single
"used" figure that silently includes both is the kind of number an employee will
dispute.

`AttendanceCalendar` pads the grid to start on the weekday the 1st actually falls
on, so the columns line up with a wall calendar.
