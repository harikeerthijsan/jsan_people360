# JSAN People360 — User Guide

*Version 1.0 · Covers every module through Payroll Phase 8*

JSAN People360 is a human-resource management system that follows a person from the first job requisition to the final settlement: hiring, onboarding, the employee record, attendance and leave, projects, performance, documents, assets, helpdesk, offboarding and payroll — with role-based access and a complete audit trail underneath all of it.

This guide is written for the people who use the product every day. It is organised by **where you are in the application** (the sidebar sections) and, within each section, by **what you are trying to do**. Screens are referred to by their sidebar names, written as **Section › Page**.

---

## Contents

1. [Getting started](#1-getting-started)
2. [How access works](#2-how-access-works)
3. [Dashboard](#3-dashboard)
4. [My Workspace — employee self-service](#4-my-workspace--employee-self-service)
5. [My Team — for managers](#5-my-team--for-managers)
6. [Organization](#6-organization)
7. [People — hiring, employees, projects, performance](#7-people--hiring-employees-projects-performance)
8. [Workforce — attendance, leave, timesheets](#8-workforce--attendance-leave-timesheets)
9. [HR Administration](#9-hr-administration)
10. [Documents](#10-documents)
11. [Assets](#11-assets)
12. [Payroll](#12-payroll)
13. [Administration — users, roles, settings, audit](#13-administration--users-roles-settings-audit)
14. [Notifications](#14-notifications)
15. [Quick reference — common tasks](#15-quick-reference--common-tasks)
16. [Troubleshooting](#16-troubleshooting)
17. [Glossary](#17-glossary)

---

## 1. Getting started

### 1.1 Signing in

> **Trying the product with demo data?** If your administrator ran the demo seed
> (`python -m app.cli.seed_demo`), sign in as any of the demo people with the
> password `Demo@12345` -- for example `ananya.rao@demo.jsan.example` (HR head),
> `vikram.singh@demo.jsan.example` (engineering manager),
> `sneha.patel@demo.jsan.example` (team lead) or `arjun.nair@demo.jsan.example`
> (engineer). Each account shows the product from that role's point of view:
> the same leave request appears in Arjun's **My Workspace**, in Sneha's
> **My Team** approvals and in Ananya's **HR Administration** queue. The
> README lists every demo account and everything the seed creates.

1. Open the application address your administrator gave you (for a local installation, `http://localhost:3000`).
2. Enter your **work email** and **password**, then select **Sign in**.
3. If your account was created for you, you may be asked to **change your password** on first sign-in.

Passwords must be at least 8 characters and contain an upper-case letter, a lower-case letter, a digit and a symbol. After **five** incorrect attempts the account is locked for **15 minutes**; the sign-in screen tells you when that has happened.

**Forgot your password?** Use **Forgot password** on the sign-in screen. A reset link is sent to your email address and expires after a short period. Administrators can also reset a password for you from **Administration › Users**.

### 1.2 Finding your way around

| Area | What it is for |
|---|---|
| **Sidebar** (left) | The main menu. It is grouped into sections — My Workspace, My Team, HR Administration, Organization, People, Workforce, Documents, Administration. You only see the pages your role can open. On small screens the menu opens from the ☰ button. |
| **Header** (top) | Breadcrumbs showing where you are, the notification bell, and your account menu (profile, change password, sign out). |
| **Dashboard** | The landing page after sign-in — key figures and graphs for the organization, or a pointer to your own workspace. |
| **Tabs in the URL** | Pages with tabs (an employee profile, for example) keep the open tab in the address, so a link you copy opens on the same tab for a colleague. |

Every list in the product supports **search, filters, sorting and pagination**; every form shows validation messages beside the field concerned; and long forms keep the **Cancel / Save** bar pinned to the bottom of the window.

### 1.3 Your account

**Administration › My Account** (available to everyone) shows your profile, lets you update the details you own — phone number, address, emergency contact — and change your password. Organizational placement (team, designation, manager) is maintained by HR and cannot be changed here.

---

## 2. How access works

Everything you can see and do is decided by **permissions**, which are grouped into **roles**. The sidebar hides pages you cannot open, and the server refuses any action you are not permitted to take — a hidden button is never the only protection.

### 2.1 Seeded roles

| Role | Intended for | In short |
|---|---|---|
| **Super Admin** | The system owner | Unrestricted. |
| **Administrator** | IT / system administration | Full application access, including users, roles, settings, the audit trail, assets and all of payroll. |
| **HR Admin** | The HR function | Runs HR end to end — people, documents, attendance, leave, recruitment, offboarding, reporting. Holds *no* payroll, user-management or role permissions unless explicitly granted. |
| **HR Executive** | HR operations staff | A narrower HR set for day-to-day processing. |
| **Recruiter** | Talent acquisition | Requisitions, openings, candidates, pipeline, interviews and offers. |
| **Project Manager** | Delivery leads | Clients, projects, allocations and the bench. |
| **Manager** | People managers | Their own direct reports: attendance and leave approvals, timesheets, performance, resignations. |
| **Team Lead** | Working leads | A lighter version of Manager for a team. |
| **Employee** | Everyone | Their own workspace only. |

Roles are data: an administrator can create new roles or change what a seeded role holds from **Administration › Roles & Permissions**.

### 2.2 Scope — "whose records?"

A permission answers *may you do this*; scope answers *to whom*. Managers and Team Leads act on **their direct reports**. Roles that hold the organization-wide permission (`employees:view_all`) — Super Admin, Administrator, HR Admin, Recruiter, Project Manager — see the whole company. This narrowing applies everywhere: directory, profiles, attendance, leave, timesheets, documents and exports.

**Payroll inverts the default.** Being somebody's manager grants *no* view of their pay. Salary and payroll pages need explicit payroll permissions, and even then reach only as far as your scope.

### 2.3 What is never deleted

The product is built on append-only history. Employment changes, salary revisions, review submissions, resignation history, asset movements, payroll exceptions and adjustments are all **recorded, never rewritten**. Where something is "removed" it is archived and can be restored. Every sensitive read (an unmasked identification number, a payslip download) and every decision is written to the **Audit Trail**.

---

## 3. Dashboard

The Dashboard is the first screen after sign-in.

**If you hold organization-wide access** you see:

- **Key figures** — active employees (with this month's joiners), present today (with the month's attendance rate), open requisitions (with offers pending), and items *waiting on somebody* (leave and corrections with no manager to decide them, documents awaiting review).
- **Headcount** — the headcount trend by month, and **Attendance today** as a breakdown of present, absent, on leave and late.
- **Hires by month** and **Leave requests by month**.
- **Month by month** — a table of headcount, hires, leave requests and attendance per month, and the **Waiting on somebody** list.

**If you do not**, the Dashboard points you to **My Workspace › My Dashboard**, which is your personal view.

Figures come from the HR dashboard and analytics services and are dated at the foot of the page.

---

## 4. My Workspace — employee self-service

Everything in this section is **yours and only yours**. These pages never take an employee ID: the system resolves who you are from your session, so there is nothing to mistype and nothing to forge.

### 4.1 My Dashboard
Today's attendance state, your leave balances, timesheet status, pending requests, recent announcements and quick links.

### 4.2 Attendance
- **Check in / Check out** for the day. Your shift (start, end, grace period, weekly-off days) decides whether an arrival counts as late or a departure as early.
- **Corrections** — if a check-in or check-out is missing or wrong, raise a *correction request* with the correct times and a reason. Your manager approves or rejects it; the original record is kept and the correction is applied on approval.
- **My calendar** shows the month with attendance, leave, holidays and weekly offs.

### 4.3 Leave
- **Balances** per leave type for the year: allocated, used, pending, remaining. Carry-forward and joining-year proration are applied automatically according to the leave policy.
- **Apply** — choose the type, dates (full or half day), and a reason; attach a document if the policy requires it. Days are counted in **working days**: weekends and holidays are not charged.
- While a request is **pending**, its days are *held* against your balance; on **approval** they are spent; on **rejection** or **withdrawal** they are released.
- Unpaid leave types (loss of pay) are deducted in payroll for the period concerned.

### 4.4 Timesheets
Weekly timesheets against the projects you are allocated to. Enter hours per day per project, save as a draft, then **submit** for approval. A submitted timesheet cannot be edited; if it is rejected you receive a comment and can resubmit.

### 4.5 Documents
Your personal documents in the Document Vault — upload (PDF, JPG or PNG), see the review status (uploaded, under review, approved, rejected), expiry warnings, and download or preview earlier versions. Every upload adds a version; nothing overwrites.

### 4.6 Projects
The projects you are allocated to, your allocation percentage and dates.

### 4.7 Holidays
The holiday calendar for your location.

### 4.8 My Profile
Your employee record: personal details, contact, addresses, bank and identification (shown masked), employment placement and history. The parts you may edit yourself are clearly marked; everything else is maintained by HR.

### 4.9 My Payroll
- **Latest payslip** with gross pay, deductions and net pay, and **View** / **Download PDF** buttons; previous payslips listed beneath.
- **Current compensation** — your salary structure and its components — plus **salary history** and every **revision** with its effective date and reason.
- Amounts appear here only for payroll that has been **finalized**; a period still being calculated or reviewed is not shown.

### 4.10 My Payslips
All official payslips, newest first, with month, pay date, gross, deductions, net pay and payslip number. **View** opens the full payslip (employer, employee, period, earnings, deductions, summary and net pay in words); **Download PDF** saves the same document. Payslips are generated from finalized payroll and cannot change.

### 4.11 My Final Settlement
After your exit has been processed, and once the organization has **settled and released** it, this page shows your final settlement: last working date, final earnings, approved encashments, approved adjustments, deductions, the settlement amount and its full breakdown. Until it is released the page says so.

### 4.12 My Requests (Helpdesk)
Raise a request to HR, IT, Admin, Finance or Facilities — category, priority, description, attachments — and follow it from *open* through *in progress* to *resolved* and *closed*. You can add comments; the agent's internal notes are never shown to you.

### 4.13 Announcements
Company notices addressed to you. Some require **acknowledgement** — select **Acknowledge** to record that you have read them.

### 4.14 My Resignation and My Offboarding
- **My Resignation** — submit a resignation with your proposed last working day and reason. The notice period comes from your employment type and is applied automatically. You can **withdraw** while it is still pending. You see your manager's decision and HR's processing.
- **My Offboarding** — once HR opens your case: the agreed last working day, the clearance progress (assets, access, handover), your **exit interview** to complete, and your **exit documents** (experience letter, relieving letter, service certificate) as they are released.

### 4.15 My Assets
Company assets currently assigned to you, with condition and expected return date. Returns are recorded by Administration.

---

## 5. My Team — for managers

Visible to anyone with direct reports and the relevant approval permissions. Everything here is limited to **your reporting line**.

| Page | What you do there |
|---|---|
| **Team Dashboard** | Who is present, on leave or absent today; pending approvals; team leave balances at a glance. |
| **Team Members** | Your direct reports' profiles (within the limits of your permissions). |
| **Team Attendance** | The team's attendance register for any date range. |
| **Team Corrections** | Approve or reject attendance correction requests. Approval applies the corrected times. |
| **Team Leave** | Approve or reject leave requests with a comment. Balances are spent on approval. |
| **Team Timesheets** | Approve or reject submitted weekly timesheets. |
| **Team Assets** | Assets held by your reports. |
| **Team Offboarding** | **Approve or reject a direct report's resignation.** This is the manager's act; HR then processes the resignation and opens the case. |
| **Team Projects** | Allocations across your team. |
| **Team Performance** | Manager reviews, goal ratings and recognition for your reports in the active cycle. |
| **Team Calendar** | A monthly view of the team's attendance, leave and holidays. |
| **Team Documents** | Your reports' documents (viewing only, unless you hold review permissions). |

---

## 6. Organization

The master data the rest of the product refers to. Each master supports create, edit, **archive** and **restore** — nothing is deleted, and a record still referenced elsewhere cannot be archived.

| Page | Contents |
|---|---|
| **Company Profile** | Legal name, registration and tax identifiers, logo, address, time zone, default currency. The company name and address appear on payslips. |
| **Business Units** | The top of the hierarchy. |
| **Teams** | Departments/teams within a business unit. "Department" throughout the product means the employee's team. |
| **Designations** | Job titles. |
| **Grades** | Grade bands (also used as salary grades). |
| **Locations** | Work locations; holiday calendars and shifts can be location-specific. |
| **Employment Types** | Permanent, contract, intern… each carrying its **notice period**, which resignations apply automatically. |

Names and codes are unique regardless of case and spacing.

---

## 7. People — hiring, employees, projects, performance

### 7.1 Workforce planning and job requisitions
A **requisition** is the request to hire: organization details, position, headcount, budget, justification, attachments. It follows a sequential approval — **Hiring manager → second approver → HR** — with every decision and comment kept in its history and in-app notifications at each step. **Workforce planning** is the dashboard over open, approved and filled requisitions.

### 7.2 Recruitment
- **Job Openings** are created from *approved* requisitions.
- **Candidates** — profiles with résumés stored in the Document Vault, skills, source and duplicate detection (email/phone).
- **Hiring Pipeline** — a drag-and-drop board through configurable recruitment stages; moving a card records a stage-history entry. Recruiter notes are private to the recruiting team.
- **Talent Pools** — keep promising candidates for later openings.
- Reports export to CSV/XLSX.

### 7.3 Interviews
Schedule interviews with **conflict checking** for interviewers and rooms, assign employee panels, and see everything on the **Interview Calendar**. Each interviewer completes a **structured scorecard**; the system calculates a recommendation, and the recruiter records the decision (advance, hold, reject). Interview materials live in the Document Vault; reports export to CSV/XLSX.

### 7.4 Offers
Build an offer from a **template** with salary components, route it through **sequential approval**, generate the **PDF** (stored in the Document Vault), **release** it to the candidate, and record acceptance, decline, withdrawal or expiry. Every version and status change is kept.

### 7.5 Preboarding & Onboarding
An accepted candidate receives a **preboarding invitation by email** and completes a portal: personal details, documents for review, and policy acknowledgements. HR reviews the submissions and **converts** the candidate into an employee record. The **onboarding case** then tracks tasks by department with progress and completion.

### 7.6 Employees
- **Employees** — the directory, with search, filters, and export to CSV/XLSX (no sensitive values, not even masked).
- **New employee** — a guided form; the employee ID (`JSAN…`) is generated automatically.
- **Employee profile** — eight tabs: overview, personal, contact & addresses, employment, documents, history, bank & identification, and activity. Bank and identification numbers are **masked**; revealing them needs a dedicated permission and every reveal is audited.
- **Lifecycle actions** — confirm probation, promote, transfer team, change designation/grade/manager/location, change status, archive/restore. Each writes an entry to the **employment history**; a change that changes nothing writes nothing. The system refuses reporting loops and will not archive a manager who still has direct reports.
- **People dashboard** — headcount, joiners and leavers, distribution by business unit, status and location.

### 7.7 Performance
**Appraisal cycles** (draft → active → closed → archived) with **weighted goals** (weightage is a budget capped at 100%), progress updates, **self review** and **manager review**, a **final review** with rating, **recognition** and **continuous feedback**. A submitted review is never rewritten. The **Performance** page gives the organization-wide overview; managers work from **My Team › Team Performance**; employees from their workspace.

### 7.8 Projects and clients
**Clients** and **projects** with members and **percentage allocations** over date ranges. The system refuses to allocate anyone beyond 100% at any point in time and keeps an allocation history. **Bench Management** lists people with spare capacity. Timesheets are validated against allocations.

---

## 8. Workforce — attendance, leave, timesheets

The organization-wide operations screens (scoped to your reporting line unless you hold `employees:view_all`).

| Page | What you do there |
|---|---|
| **Overview** | Today's attendance summary, pending corrections, leave and timesheet approvals. |
| **Attendance Register** | Every attendance record by date range and employee; export to CSV/XLSX/PDF. |
| **Attendance Calendar** | A monthly calendar across the workforce. |
| **Corrections** | Correction requests awaiting decision. |
| **Shifts** | Define shifts: start/end, grace minutes, weekly-off days. |
| **Shift Assignments** | Assign shifts to employees with effective dates. |
| **Leave** | All leave requests with filters; **Leave Approvals** is the queue. |
| **Leave Types** | Paid/unpaid, annual allocation, carry-forward and its cap, credit frequency, whether negative balances are allowed, whether a document is required. |
| **Holiday Calendars** | Named calendars with holiday dates, optionally per location. Holidays are never charged as leave. |
| **Timesheets** / **Timesheet Approvals** | All timesheets and the approval queue. |
| **Reports** | Six workforce reports (attendance, late arrivals, leave, balances, timesheets, overtime) in CSV/XLSX/PDF. |

Four rules to remember: a day belongs to one attendance record; leave is counted in working days; a balance is held on application and spent on approval; a submitted timesheet is not edited.

---

## 9. HR Administration

The HR view across the company. HR is **not** an administrator — these pages never touch users, roles, settings or the audit trail, and an HR user without organization-wide scope sees only their own reporting line.

| Page | What you do there |
|---|---|
| **HR Dashboard** | The composite picture: employees, attendance, leave, recruitment, documents, performance and requests waiting on somebody. |
| **HR Employees** | The directory with HR actions. |
| **HR Attendance / HR Leave / HR Timesheets** | Organization-wide registers and decisions. |
| **Leave Policies** | Configure leave types and policy parameters. |
| **Workforce Allocation** | Allocation and bench view across projects. |
| **Document Reviews** | The queue of employee documents awaiting review — approve or reject with a comment. |
| **Performance Overview** | Cycle progress and completion across the organization. |
| **HR Recruitment** | Recruitment from the HR side. |
| **Helpdesk** | The **agent's queue**: assign, respond, add internal notes (never shown to the requester), resolve and close. |
| **Announcements** | **Draft** announcements with an audience (everyone, business unit, team, location) and an acknowledgement requirement; **publish** sends them through the notification inbox. Drafting and publishing are separate permissions. |
| **Employee Assets** | What each employee holds — used to run exit clearances. |
| **Offboarding** | Process resignations (verify notice period, agree the last working day, open the case), run the five-department clearance (HR, manager, IT, admin, finance), track handover, exit interviews, exit documents and the settlement status. Completing a case sets the employee inactive **and disables their login**. |
| **HR Reports** | Cross-module HR reports with CSV/XLSX export. |

---

## 10. Documents

The **Document Vault** stores files for employees, candidates, users and the organization.

- **Categories & Types** (`Documents › Categories & Types`) — configure what can be uploaded and whether a type expires.
- Uploads accept PDF, JPEG and PNG only; the file signature is checked, not just the extension.
- Every upload is a **new version**; previous versions remain downloadable.
- Documents carry a **review status** (uploaded → under review → approved/rejected) and an **expiry state** (valid, expiring soon, expired).
- Preview and download always go through the application — files are never exposed by a direct link.
- Archive and restore, dashboards, and a document-scoped audit trail.

---

## 11. Assets

The asset register belongs to **Administration**; HR can view holdings but cannot issue or write off property.

| Page | What you do there |
|---|---|
| **Asset Register** | Every asset: code, tag, category, brand/model, serial, purchase and warranty details, location, condition, status, and who holds it now. |
| **Asset Dashboard** | Counts by status and category, unassigned stock, warranties expiring. |
| **Asset detail** | **Assign** to an employee, **return** (with condition, damage, missing accessories), **transfer** between employees, and the full **history** of every movement. |
| **Asset Maintenance** | Log repairs and servicing with vendor, cost and status; a damaged asset must pass through maintenance before it is available again. |
| **Asset Reports** | Assigned, available, warranty and maintenance reports in CSV/XLSX. |

Status moves only along the allowed transitions — nothing comes back from *disposed*.

---

## 12. Payroll

Payroll is a controlled path from salary setup to an immutable result:

```
Components & structures → employee compensation → configuration & periods
→ inputs (attendance, leave, overtime snapshot) → calculation → review & adjustments
→ reconciliation → approval → finalization → payslips, reports, final settlement
```

Payroll permissions are granted **only explicitly**. Administrators hold all of them; HR and managers hold none by default. Each stage below names the permission it needs.

### 12.1 Setting up

**Salary Components** (`payroll:component_manage`) — earnings and deductions, each fixed or a percentage of basic/gross, with behaviour flags: *prorated*, *affected by attendance*, *affected by unpaid leave*, *counts toward the overtime base*, *taxable*.

**Salary Structures** (`payroll:structure_manage`) — templates that group components with default values, a pay frequency and a currency. A structure must be *active* before it is assigned.

**Employee Compensation** (`payroll:view`, `payroll:create`, `payroll:update`) — assign a structure to an employee with annual CTC, annual and monthly gross, basic salary, component values and an effective date. **Revising** a salary ends the current record and opens a new one from the new effective date; both are kept and the **salary history** records the change, its reason and who made it. Overlapping periods are refused.

**Payroll Settings** (`payroll:config_view` / `payroll:config_manage`) — one configuration: pay frequency and period days, working-days rule and weekly offs, holiday calendar, proration basis (calendar or working days), unpaid-leave treatment and basis, overtime (enabled, basis, multiplier, minimum/maximum hours, approval required, standard daily hours), attendance deductions, and the rounding rule. Every change needs a **reason** and an **effective date**, and is kept in the configuration history.

**Payroll Periods** (`payroll:period_manage`) — the month (or week) being paid, with start, end and pay dates. Periods move open → processing → under review → approved → finalized; a finalized period is closed for good.

**Payroll Rules** (`payroll:rule_manage`) — for each leave type, whether it is paid or deducted, and on what basis.

**Employee Payroll Settings** (`payroll:employee_settings_view` / `_update`) — eligibility (eligible, not eligible with a reason, suspended) and per-employee overrides for frequency, proration, overtime and unpaid-leave deduction. **Employees are not paid unless marked eligible.**

### 12.2 The monthly cycle

**1. Payroll Inputs** (`payroll:inputs_prepare`, `payroll:inputs_view`, `payroll:inputs_review`).
Select the period and **Prepare inputs**. For every eligible employee the system snapshots calendar, working, eligible and present days, paid and unpaid leave, approved and pending overtime, joining and exit dates — **reading** attendance and leave, never changing them. Problems (missing check-out, unresolved correction, unapproved overtime, invalid leave, missing salary…) are flagged as **exceptions** and the input is marked *Requires review*. Later, **Detect changes** compares the snapshot's fingerprint with the source records and flags anything that changed since. A reviewer can mark a flagged input reviewed with a note.

**2. Payroll Runs** (`payroll:runs_view`, `payroll:run_create`, `payroll:calculate`, `payroll:recalculate`).
Create one run for the period (only one is allowed) and **Calculate**. The engine consumes the input snapshot only — never raw attendance — and produces one record per employee with a full **line-item breakdown**: each component with its basis (e.g. "40% of basic · 17/31 calendar days"), overtime pay, unpaid-leave deduction, gross, deductions and net. Mid-period salary revisions are split into segments. If the engine cannot be sure — no salary, overlapping salary records, a flagged input — it **refuses** that employee with a stated reason rather than guessing. **Recalculate** replaces the run's records whole and is allowed until the run is submitted for approval.

**3. Payroll Review** (`payroll:review_view`, `payroll:exception_resolve`, `payroll:adjustment_create`, `payroll:adjustment_update`, `payroll:review_complete`).
The review dashboard lists calculated runs with their exception load. On a run's review page:
- **Exceptions** are graded *warning*, *error* or *critical*. Resolve one with a reason — it is never deleted — and resolutions carry over if the same issue reappears after a recalculation. **Critical exceptions block review completion.**
- **Mark records** reviewed or *adjustment required*.
- **Adjustments** are additive only: a positive amount, earning or deduction, with a mandatory reason. The original calculation is never edited; the record shows **Original · Adjustment · Final**. Cancelling an adjustment marks it cancelled with a reason and backs the amount out. Adjustments survive recalculation.
- **Checklist** — nine items to tick; recalculation resets them.
- **Comments** — append-only.
- **Reconciliation** — original, adjustment and final totals, and a comparison with the previous period that **highlights** large movements (never rejects them).
- **Complete review** is refused until every checklist item is ticked, no critical exception is open and no record still requires review or an adjustment.

**4. Payroll Approval** (`payroll:approval_view`, `payroll:approve`, `payroll:return`).
The reviewer **submits** a completed review; the run becomes *pending approval* and its numbers freeze. The approval page shows payroll, employee and review summaries, the full trail of submissions, and every blocker verbatim. An approver **approves** with a mandatory comment (the gates are re-checked at that moment) or **returns** the run with a reason, which reopens it for review and recalculation. Nothing skips a state.

**5. Finalization** (`payroll:finalize`).
An approved run is **finalized**: one immutable, fully denormalized **snapshot** per employee is written (names, dates, line items, adjustments, who approved and finalized), the run is locked against every change, and the period closes. Later changes to salary, attendance or leave cannot touch it — any attempt is refused and audited. **Payroll History** lists finalized runs read-only.

**6. Payslips** (`payroll:payslip_generate`, `payroll:payslip_view`, `payroll:payslip_download`).
From a finalized run's approval page, **Generate payslips** creates one official payslip per employee (excluded employees are skipped) numbered `PS-YYYY-MM-EMPLOYEEID`. The PDF shows employer, employee, period, earnings and deductions with their bases, totals and the net amount in words. **Regenerating** rebuilds the file from the same snapshot — the number and every figure stay identical. Employees see their own payslips in My Workspace; administrators use **Payslips** with filters by employee, month, department and number.

### 12.3 Payroll Reports (`payroll:report_view`, `payroll:report_export`)
Filter by period, date range, department, location, employee and payroll status (finalized by default — the official figures). Six views: **Summary** (employee count, gross, deductions, net, adjustments, overtime, unpaid leave, employer cost), **Monthly payroll**, **Earnings** (basic, allowances, bonus, overtime, other), **Deductions**, **Overtime** and **Unpaid leave**. Export any view as **CSV** or **XLSX**. Employer cost is shown as gross payroll — employer contributions are not modelled.

### 12.4 Final Settlement (`payroll:settlement_view`, `_create`, `_update`, `_approve`, `_finalize`)
Connected to Offboarding — it never starts a resignation. The **Final Settlement** page lists every exiting employee with joining date, last working date, exit type and reason, final payroll period and settlement status (*not started, draft, under review, approved, settled*). An employee is eligible once their offboarding case is in progress or completed and a compensation record exists.

**Start settlement** opens and calculates it from existing data: final salary for the days after the last finalized payroll up to the last working date, unpaid leave and recorded overtime in that window, leave balances (eligible, used, remaining), and assets on loan with their clearance status. Anything that needs a company decision — leave encashment, a bonus, an asset recovery, an advance — is proposed as an **adjustment** with a reason and counts only once an approver **approves** it; rejected adjustments stay on record. The settlement is stored as its components — final earnings + approved encashments + approved adjustments − final deductions — never as one number.

Workflow: **Submit for review → Complete review → Approve** (requires the review complete and no critical issue, such as an unreturned asset without an approved recovery or a pending adjustment) **→ Settle**. Settling freezes the settlement, stores its snapshot, releases it to the employee's workspace and marks the offboarding tracker complete. An approved settlement can be **reopened** with a reason; a settled one cannot change.

### 12.5 Payroll at a glance — who does what

| Stage | Permission(s) | Seeded holders |
|---|---|---|
| Set up components, structures, configuration | `component_manage`, `structure_manage`, `config_manage`, `period_manage`, `rule_manage` | Administrator |
| Assign / revise salary | `create`, `update`; view with `view` / `team_view` / `history_view` | Administrator |
| Prepare and review inputs | `inputs_prepare`, `inputs_view`, `inputs_review` | Administrator |
| Create and calculate runs | `run_create`, `calculate`, `recalculate`, `runs_view`, `record_view` | Administrator |
| Review, resolve, adjust, complete | `review_view`, `exception_resolve`, `adjustment_create`, `adjustment_update`, `review_complete` | Administrator |
| Approve, return, finalize | `approval_view`, `approve`, `return`, `finalize`, `finalized_view` | Administrator |
| Payslips | `payslip_view`, `payslip_generate`, `payslip_download` | Administrator |
| Reports and settlement | `report_view`, `report_export`, `settlement_*` | Administrator |
| Own compensation, payslips, settlement | *(no permission — always your own)* | Everyone |

Grant individual permissions to an HR role from **Roles & Permissions** to delegate specific stages — for instance `review_*` to a payroll executive and `approve` to a finance approver — which keeps preparation and approval in different hands.

---

## 13. Administration — users, roles, settings, audit

| Page | What you do there |
|---|---|
| **Users** | Create accounts (staff code `USR-…` is generated), assign roles, place users in the organization, activate/deactivate, archive/restore, and **reset passwords**. You cannot deactivate yourself or the last active administrator. |
| **Roles & Permissions** | Create roles and tick permissions per module and action. Seeded roles can be adjusted. What a session cannot open is hidden from it; the server refuses it regardless. |
| **Settings** | Application settings (security parameters, defaults) with a change history. |
| **Audit Trail** | Every recorded action — who, what, when, on which record, outcome, and context — searchable by user, action, entity and date, with CSV export. Sensitive reads, payroll decisions, denied attempts and modification attempts on locked records all appear here. |

---

## 14. Notifications

The bell in the header shows your inbox: approvals that need you, decisions on your requests, interview assignments, requisition and offer steps, published announcements, and helpdesk updates. Selecting a notification opens the record it refers to. Preboarding invitations are the one message sent by email, because the recipient has no account yet.

---

## 15. Quick reference — common tasks

| I want to… | Go to |
|---|---|
| Check in for the day | My Workspace › My Dashboard (or Attendance) › **Check in** |
| Fix a missed check-out | My Workspace › Attendance › **Request correction** |
| Apply for leave | My Workspace › Leave › **Apply** |
| Approve my team's leave | My Team › **Team Leave** |
| Submit my timesheet | My Workspace › Timesheets › **Submit** |
| Download my payslip | My Workspace › **My Payslips** › Download PDF |
| See my salary structure | My Workspace › **My Payroll** |
| Raise a request to IT/HR | My Workspace › **My Requests** › New request |
| Resign | My Workspace › **My Resignation** |
| Add a new employee | People › Employees › **New employee** |
| Change someone's manager or team | People › Employees › profile › **Employment** actions |
| Open a requisition | People › **Job Requisitions** › New |
| Move a candidate along | People › **Hiring Pipeline** (drag the card) |
| Schedule an interview | People › **Interviews** › Schedule |
| Make an offer | People › **Offers** › New offer |
| Review a document | HR Administration › **Document Reviews** |
| Publish an announcement | HR Administration › **Announcements** › Draft → Publish |
| Process a resignation | HR Administration › **Offboarding** |
| Assign a laptop | Administration › **Asset Register** › asset › Assign |
| Assign a salary | Administration › **Employee Compensation** › employee › Assign |
| Run this month's payroll | Payroll Inputs › Prepare → Payroll Runs › Create & Calculate → Payroll Review → Approval › Submit → Approve → Finalize → Generate payslips |
| Settle a leaver | Administration › **Final Settlement** › Start settlement |
| Export payroll figures | Administration › **Payroll Reports** › Export CSV / XLSX |
| Reset a user's password | Administration › **Users** › user › Reset password |
| See who did what | Administration › **Audit Trail** |

---

## 16. Troubleshooting

| Symptom | Likely cause and what to do |
|---|---|
| "Unable to sign in" and the page does not respond | The API server is not running or not reachable from the browser. An administrator should confirm the backend is up (its `/docs` page loads). |
| "Too many failed attempts" | The account is locked for 15 minutes after five wrong passwords. Wait, or ask an administrator to reset the password. |
| A page or button I expect is missing | Your role does not hold the permission. Menus hide what you cannot open. Ask an administrator to review your role in **Roles & Permissions**. |
| A manager cannot see a report's salary | By design. Payroll needs explicit payroll permissions; the reporting line grants nothing. |
| "This run is locked" | The payroll run has been submitted, approved or finalized. Return it for correction (approval page) if it is still pending; a finalized run cannot change. |
| "Review cannot be completed" | Tick every checklist item, resolve all *critical* exceptions, and clear records marked *requires review* / *adjustment required* (fix the cause and recalculate). The readiness panel lists each blocker. |
| Payslip not visible to the employee | Payslips exist only for **finalized** runs and only after **Generate payslips** has been run. |
| Leave request refused | Insufficient balance (unless the type allows negative), overlapping request, weekend/holiday-only range, or a required document is missing. |
| Timesheet refused | Hours logged against a project you are not allocated to on that day, or the week is already submitted. |
| Cannot archive a record | Something still references it (a team with members, a manager with reports, a category with documents). Move the dependants first. |

---

## 17. Glossary

| Term | Meaning |
|---|---|
| **Adjustment (payroll)** | An additive, reasoned change layered on a calculated record; never edits the original. |
| **Business unit / Team / Designation / Grade** | The organization hierarchy and reference masters. "Department" means team. |
| **Clearance** | The per-department sign-off (HR, manager, IT, admin, finance) during offboarding. |
| **Compensation record** | An employee's salary for a period — structure, components, CTC, effective dates. A revision opens a new record. |
| **Correction (attendance)** | A request to fix a check-in/out, decided by the manager. |
| **Critical exception** | A payroll issue that blocks review completion and approval until resolved. |
| **Final snapshot** | The immutable per-employee record written when payroll is finalized; payslips are rendered from it. |
| **Full & Final (F&F) settlement** | The exit settlement — final salary, encashments, adjustments and deductions — over the offboarding case. |
| **Payroll input** | The per-employee snapshot of attendance, leave and overtime a run is calculated from. |
| **Payroll period / run** | The time span being paid, and the single calculation execution for it. |
| **Proration** | Paying a component in proportion to eligible days (calendar or working days). |
| **Requisition** | An approved request to hire, from which a job opening is created. |
| **Scope** | Whose records a permission reaches: your reporting line, or the whole organization with `employees:view_all`. |
| **Talent pool** | A saved group of candidates for future openings. |
| **Timesheet** | Weekly hours per project, validated against allocations. |

---

*For installation, configuration and API details see the technical documentation in the `docs/` folder (Installation, Architecture, API, RBACModule and the per-module guides).*
