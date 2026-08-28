"""Enumerations shared across domain models."""

from __future__ import annotations

from enum import StrEnum


class RecordStatus(StrEnum):
    """Business status of a master-data record.

    Deliberately distinct from soft deletion. A record can be:

    * ``active``   -- available for selection in other modules
    * ``inactive`` -- retained and referenceable, but hidden from new selections
    * *archived*   -- ``deleted_at`` is set; excluded from every read by default

    Deactivating is reversible and visible; archiving removes the record from
    normal use without destroying the rows that reference it.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"


#: SQL fragment used by the CHECK constraint on every ``status`` column.
RECORD_STATUS_SQL_VALUES = ", ".join(f"'{status.value}'" for status in RecordStatus)


class Gender(StrEnum):
    """Gender recorded against a user.

    ``PREFER_NOT_TO_SAY`` is a first-class option rather than a blank: an
    unanswered field and a declined answer are different facts, and conflating
    them makes the data unusable for the diversity reporting HR systems are
    routinely asked for.
    """

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


GENDER_SQL_VALUES = ", ".join(f"'{gender.value}'" for gender in Gender)


def _sql_values(enum: type[StrEnum]) -> str:
    """Render an enum as the value list of a SQL ``IN`` clause.

    Every one of these enums is stored as a ``varchar`` with a CHECK constraint
    rather than a PostgreSQL ``ENUM`` type: adding a value to a native enum needs
    ``ALTER TYPE`` and cannot be rolled back inside a transaction, which makes an
    otherwise trivial migration irreversible.
    """
    return ", ".join(f"'{member.value}'" for member in enum)


class BloodGroup(StrEnum):
    """ABO/Rh blood group, recorded for emergency contact purposes."""

    A_POSITIVE = "A+"
    A_NEGATIVE = "A-"
    B_POSITIVE = "B+"
    B_NEGATIVE = "B-"
    AB_POSITIVE = "AB+"
    AB_NEGATIVE = "AB-"
    O_POSITIVE = "O+"
    O_NEGATIVE = "O-"


BLOOD_GROUP_SQL_VALUES = _sql_values(BloodGroup)


class MaritalStatus(StrEnum):
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"
    SEPARATED = "separated"


MARITAL_STATUS_SQL_VALUES = _sql_values(MaritalStatus)


class EmploymentStatus(StrEnum):
    """Where an employee sits in the employment lifecycle.

    Distinct from :class:`RecordStatus` and from soft deletion. An employee on
    ``NOTICE_PERIOD`` is still employed and still appears everywhere; an archived
    employee is hidden from normal reads regardless of this value.
    """

    PROBATION = "probation"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    NOTICE_PERIOD = "notice_period"
    RESIGNED = "resigned"
    INACTIVE = "inactive"


EMPLOYMENT_STATUS_SQL_VALUES = _sql_values(EmploymentStatus)

#: Statuses that mean the person is still employed. Used to scope headcount and
#: to decide whether an employee may be selected as a reporting manager.
EMPLOYED_STATUSES: frozenset[EmploymentStatus] = frozenset(
    {
        EmploymentStatus.PROBATION,
        EmploymentStatus.CONFIRMED,
        EmploymentStatus.ACTIVE,
        EmploymentStatus.NOTICE_PERIOD,
    }
)


class WorkMode(StrEnum):
    OFFICE = "office"
    REMOTE = "remote"
    HYBRID = "hybrid"


WORK_MODE_SQL_VALUES = _sql_values(WorkMode)


class AddressType(StrEnum):
    """An employee holds at most one address of each type."""

    CURRENT = "current"
    PERMANENT = "permanent"


ADDRESS_TYPE_SQL_VALUES = _sql_values(AddressType)


class EmploymentChangeType(StrEnum):
    """What a row of the employment history records.

    ``CREATED`` is the opening row written when the employee is first saved, so
    the history is a complete account of the placement from day one rather than
    starting at the first amendment.
    """

    CREATED = "created"
    CONFIRMATION = "confirmation"
    PROMOTION = "promotion"
    TEAM_TRANSFER = "team_transfer"
    DESIGNATION_CHANGE = "designation_change"
    GRADE_CHANGE = "grade_change"
    MANAGER_CHANGE = "manager_change"
    LOCATION_CHANGE = "location_change"
    STATUS_CHANGE = "status_change"
    DETAILS_UPDATED = "details_updated"


EMPLOYMENT_CHANGE_TYPE_SQL_VALUES = _sql_values(EmploymentChangeType)


class DocumentOwnerType(StrEnum):
    """What a document belongs to.

    The vault is deliberately not tied to employees: recruitment will attach
    résumés to candidates, and the organization holds its own registrations and
    policies. Owner type plus owner id is a polymorphic reference, so there is
    no foreign key -- the service checks the target exists for the types it
    knows, and a new owner type is one enum member rather than a new table.
    """

    EMPLOYEE = "employee"
    CANDIDATE = "candidate"
    ORGANIZATION = "organization"
    USER = "user"


DOCUMENT_OWNER_TYPE_SQL_VALUES = _sql_values(DocumentOwnerType)

#: Owner types whose target can be verified: every one of them.
#:
#: ``candidate`` was excluded while Recruitment was unbuilt, which left the one
#: owner type the vault was designed for as the only unchecked one. The table
#: exists now, so the check applies to all four and a document can no longer be
#: filed against a candidate who does not exist.
VERIFIABLE_OWNER_TYPES: frozenset[DocumentOwnerType] = frozenset(DocumentOwnerType)


class DocumentStatus(StrEnum):
    """Where a document sits in its review lifecycle.

    Separate from expiry, which is derived from a date rather than set by a
    person, and separate from archiving, which hides the record entirely.
    """

    UPLOADED = "uploaded"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ARCHIVED = "archived"


DOCUMENT_STATUS_SQL_VALUES = _sql_values(DocumentStatus)


class ExpiryState(StrEnum):
    """Derived from the expiry date; never stored.

    Computed on read so it cannot go stale. A stored "expiring soon" would be
    wrong the morning after it was written, and correcting it would need a
    scheduled job to be running.
    """

    NONE = "none"
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"


#: How far ahead counts as "expiring soon".
EXPIRY_WARNING_DAYS = 30


# ----------------------------------------------------------------------
# Performance Management
# ----------------------------------------------------------------------
class PerformanceCycleStatus(StrEnum):
    """Where an appraisal cycle sits in its own lifecycle.

    ``DRAFT`` is where a cycle is configured; only an ``ACTIVE`` cycle accepts
    goals and reviews. ``CLOSED`` means every final rating is in, and
    ``ARCHIVED`` takes it out of normal view without destroying a year of
    performance data.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


PERFORMANCE_CYCLE_STATUS_SQL_VALUES = _sql_values(PerformanceCycleStatus)


class GoalStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


GOAL_STATUS_SQL_VALUES = _sql_values(GoalStatus)

#: Goal states that still count towards an employee's committed weightage.
#: A cancelled goal is deliberately excluded -- it was called off, so holding
#: its weightage against the 100% budget would block re-planning the year.
LIVE_GOAL_STATUSES: frozenset[GoalStatus] = frozenset(
    {GoalStatus.NOT_STARTED, GoalStatus.IN_PROGRESS, GoalStatus.COMPLETED, GoalStatus.BLOCKED}
)


class GoalPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


GOAL_PRIORITY_SQL_VALUES = _sql_values(GoalPriority)


class ReviewStage(StrEnum):
    """Which party a rating came from.

    Self and manager ratings have exactly the same shape -- a score against one
    goal, with comments -- so they share a table and are told apart by this.
    """

    SELF = "self"
    MANAGER = "manager"


REVIEW_STAGE_SQL_VALUES = _sql_values(ReviewStage)


class ReviewStatus(StrEnum):
    """A review is a draft until it is submitted, and never edited after."""

    DRAFT = "draft"
    SUBMITTED = "submitted"


REVIEW_STATUS_SQL_VALUES = _sql_values(ReviewStatus)


class PerformanceRecommendation(StrEnum):
    """What a manager proposes as an outcome.

    Deliberately a *recommendation*: this module records the proposal and
    nothing else. Acting on one -- a salary revision, an actual promotion -- is
    Payroll's and HR's business, and is explicitly out of scope here.
    """

    PROMOTION = "promotion"
    SALARY_REVISION = "salary_revision"
    TRAINING = "training"
    PIP = "pip"
    NONE = "none"


PERFORMANCE_RECOMMENDATION_SQL_VALUES = _sql_values(PerformanceRecommendation)


class RecognitionType(StrEnum):
    STAR_PERFORMER = "star_performer"
    INNOVATION = "innovation"
    TEAM_PLAYER = "team_player"
    CUSTOMER_APPRECIATION = "customer_appreciation"
    LEADERSHIP = "leadership"


RECOGNITION_TYPE_SQL_VALUES = _sql_values(RecognitionType)


class FeedbackCategory(StrEnum):
    APPRECIATION = "appreciation"
    SUGGESTION = "suggestion"
    IMPROVEMENT = "improvement"
    ACHIEVEMENT = "achievement"
    RECOGNITION = "recognition"


FEEDBACK_CATEGORY_SQL_VALUES = _sql_values(FeedbackCategory)


class FeedbackVisibility(StrEnum):
    """Who may read a piece of continuous feedback.

    ``PRIVATE`` is between the two people involved, ``MANAGER`` adds the
    recipient's reporting line, and ``PUBLIC`` is visible to anyone who can see
    the employee. Enforced when the feedback is read, not when it is written.
    """

    PRIVATE = "private"
    MANAGER = "manager"
    PUBLIC = "public"


FEEDBACK_VISIBILITY_SQL_VALUES = _sql_values(FeedbackVisibility)

#: The inclusive rating scale used by every review stage.
MIN_RATING = 1
MAX_RATING = 5

#: Total goal weightage an employee may carry in one cycle.
TOTAL_WEIGHTAGE = 100

#: A final rating at or below this is surfaced as a low-performance alert.
LOW_PERFORMANCE_RATING = 2


# ----------------------------------------------------------------------
# Workforce Operations
# ----------------------------------------------------------------------
class ShiftType(StrEnum):
    GENERAL = "general"
    MORNING = "morning"
    EVENING = "evening"
    NIGHT = "night"
    FLEXIBLE = "flexible"


SHIFT_TYPE_SQL_VALUES = _sql_values(ShiftType)


class AttendanceStatus(StrEnum):
    """What a single day amounts to.

    ``HOLIDAY`` and ``WEEKEND`` are recorded rather than left blank: a missing
    row and a day nobody was expected to work look identical otherwise, and the
    monthly percentage would be wrong for every employee.
    """

    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    LEAVE = "leave"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"


ATTENDANCE_STATUS_SQL_VALUES = _sql_values(AttendanceStatus)

#: Statuses that count towards the monthly attendance percentage. A holiday or a
#: weekend is neither present nor absent -- counting them either way distorts it.
COUNTED_ATTENDANCE_STATUSES: frozenset[AttendanceStatus] = frozenset(
    {
        AttendanceStatus.PRESENT,
        AttendanceStatus.ABSENT,
        AttendanceStatus.HALF_DAY,
        AttendanceStatus.LEAVE,
    }
)

#: What each counted status contributes to "days attended".
ATTENDANCE_CREDIT: dict[str, float] = {
    AttendanceStatus.PRESENT.value: 1.0,
    AttendanceStatus.HALF_DAY.value: 0.5,
    AttendanceStatus.LEAVE.value: 0.0,
    AttendanceStatus.ABSENT.value: 0.0,
}


class ApprovalStatus(StrEnum):
    """Shared by every request a manager acts on."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


APPROVAL_STATUS_SQL_VALUES = _sql_values(ApprovalStatus)

#: A request in one of these has been decided and cannot be decided again.
DECIDED_STATUSES: frozenset[ApprovalStatus] = frozenset(
    {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED}
)


class LeaveDayPart(StrEnum):
    """How much of a day a leave request covers.

    Half days are only meaningful on a single-day request; the service refuses
    the combination rather than silently rounding it.
    """

    FULL_DAY = "full_day"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"


LEAVE_DAY_PART_SQL_VALUES = _sql_values(LeaveDayPart)


class CreditFrequency(StrEnum):
    """How often a leave type's entitlement is credited.

    Configuration for the policy screen rather than a scheduler: the platform
    credits the annual figure in one go when a balance row is first read, and
    this records the schedule a proportional engine would follow. ``NONE`` is
    for the types nobody accrues -- loss of pay, and anything granted case by
    case.
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"
    NONE = "none"


CREDIT_FREQUENCY_SQL_VALUES = _sql_values(CreditFrequency)

#: Credit periods in a year, for validating that a schedule adds up to at most
#: the annual maximum. ``NONE`` accrues nothing, so it has no periods.
CREDIT_PERIODS_PER_YEAR: dict[str, int] = {
    CreditFrequency.MONTHLY.value: 12,
    CreditFrequency.QUARTERLY.value: 4,
    CreditFrequency.ANNUALLY.value: 1,
    CreditFrequency.NONE.value: 0,
}


class HolidayType(StrEnum):
    PUBLIC = "public"
    RESTRICTED = "restricted"
    OPTIONAL = "optional"


HOLIDAY_TYPE_SQL_VALUES = _sql_values(HolidayType)


class TimesheetStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


TIMESHEET_STATUS_SQL_VALUES = _sql_values(TimesheetStatus)


class ResignationStatus(StrEnum):
    """Where a separation sits between the employee's intent and their exit.

    The order below is the order of the workflow, and the transition table in
    :mod:`app.services.offboarding_service` is the only place it is enforced --
    a status is data, and a status *change* is a rule.

    ``WITHDRAWN`` and ``CANCELLED`` are deliberately distinct. An employee
    withdraws their own resignation before it is approved; HR or an
    administrator cancels one that has already been approved, which is a
    different event with a different audit trail and different consequences for
    the offboarding case underneath it.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    MANAGER_REVIEW = "manager_review"
    HR_REVIEW = "hr_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    NOTICE_PERIOD = "notice_period"
    CLEARANCE = "clearance"
    EXIT_INTERVIEW = "exit_interview"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


RESIGNATION_STATUS_SQL_VALUES = _sql_values(ResignationStatus)

#: Statuses in which a resignation is still being decided, and from which the
#: employee may still withdraw it themselves.
WITHDRAWABLE_RESIGNATION_STATUSES: frozenset[ResignationStatus] = frozenset(
    {
        ResignationStatus.DRAFT,
        ResignationStatus.SUBMITTED,
        ResignationStatus.MANAGER_REVIEW,
        ResignationStatus.HR_REVIEW,
    }
)

#: Statuses that mean the separation is over, one way or another. Nothing
#: transitions out of these.
TERMINAL_RESIGNATION_STATUSES: frozenset[ResignationStatus] = frozenset(
    {
        ResignationStatus.REJECTED,
        ResignationStatus.WITHDRAWN,
        ResignationStatus.COMPLETED,
        ResignationStatus.CANCELLED,
    }
)

#: Statuses that mean an approved separation is in progress. An employee with a
#: resignation in one of these is on their way out and the offboarding case
#: exists.
ACTIVE_OFFBOARDING_STATUSES: frozenset[ResignationStatus] = frozenset(
    {
        ResignationStatus.APPROVED,
        ResignationStatus.NOTICE_PERIOD,
        ResignationStatus.CLEARANCE,
        ResignationStatus.EXIT_INTERVIEW,
    }
)


class OffboardingCaseStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


OFFBOARDING_CASE_STATUS_SQL_VALUES = _sql_values(OffboardingCaseStatus)


class OffboardingTaskStatus(StrEnum):
    """``WAIVED`` is a completion, not a skip.

    A task nobody has to do -- an asset the employee never held, a system they
    never had -- still has to be answered before clearance is final, or the
    checklist stalls on rows that will never be ticked. Waiving records who
    decided it did not apply.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAIVED = "waived"


OFFBOARDING_TASK_STATUS_SQL_VALUES = _sql_values(OffboardingTaskStatus)

#: Task states that no longer block final clearance.
SETTLED_TASK_STATUSES: frozenset[OffboardingTaskStatus] = frozenset(
    {OffboardingTaskStatus.COMPLETED, OffboardingTaskStatus.WAIVED}
)


class OffboardingDepartment(StrEnum):
    """Who owns a checklist row. Not a role and not a permission.

    The department decides which dashboard a task appears on and who is
    nominated as its owner when the case is created; what a person may *do* to
    it is still decided by their permissions and their scope.
    """

    HR = "hr"
    MANAGER = "manager"
    IT = "it"
    ADMIN = "admin"
    FINANCE = "finance"


OFFBOARDING_DEPARTMENT_SQL_VALUES = _sql_values(OffboardingDepartment)


class HandoverStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


HANDOVER_STATUS_SQL_VALUES = _sql_values(HandoverStatus)


class AssetReturnStatus(StrEnum):
    ASSIGNED = "assigned"
    RETURNED = "returned"
    DAMAGED = "damaged"
    LOST = "lost"
    WAIVED = "waived"


ASSET_RETURN_STATUS_SQL_VALUES = _sql_values(AssetReturnStatus)

#: Asset states that no longer block clearance. Damaged and lost are settled
#: outcomes: the item is accounted for, and what it costs is Finance's row on
#: the checklist rather than a reason to hold the whole exit open.
SETTLED_ASSET_STATUSES: frozenset[AssetReturnStatus] = frozenset(
    {
        AssetReturnStatus.RETURNED,
        AssetReturnStatus.DAMAGED,
        AssetReturnStatus.LOST,
        AssetReturnStatus.WAIVED,
    }
)


class AccessClearanceStatus(StrEnum):
    """Tracked, not performed.

    Nothing in this MVP reaches out to a mail server or an identity provider.
    ``REVOKED`` records that somebody in IT did it and said so.
    """

    PENDING = "pending"
    REVOKED = "revoked"
    NOT_APPLICABLE = "not_applicable"


ACCESS_CLEARANCE_STATUS_SQL_VALUES = _sql_values(AccessClearanceStatus)

SETTLED_ACCESS_STATUSES: frozenset[AccessClearanceStatus] = frozenset(
    {AccessClearanceStatus.REVOKED, AccessClearanceStatus.NOT_APPLICABLE}
)


class SettlementStatus(StrEnum):
    """Full & final *tracking*. No figure in this module is a calculation.

    Payroll is a future module. What is recorded here is where the settlement
    has got to and the reference somebody in Finance can quote -- deliberately
    not salary, tax, PF, ESI or gratuity, none of which this system is entitled
    to guess at.
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PENDING_CLEARANCE = "pending_clearance"
    READY_FOR_PROCESSING = "ready_for_processing"
    COMPLETED = "completed"


SETTLEMENT_STATUS_SQL_VALUES = _sql_values(SettlementStatus)


class ExitDocumentType(StrEnum):
    EXPERIENCE_LETTER = "experience_letter"
    RELIEVING_LETTER = "relieving_letter"
    SERVICE_CERTIFICATE = "service_certificate"


EXIT_DOCUMENT_TYPE_SQL_VALUES = _sql_values(ExitDocumentType)


# ----------------------------------------------------------------------
# Asset Management
# ----------------------------------------------------------------------
class AssetStatus(StrEnum):
    """Where an asset is in its own lifecycle.

    Distinct from *condition*, which describes the physical state of the thing.
    A laptop can be ``ASSIGNED`` and ``DAMAGED`` at the same time: somebody has
    it, and it has a cracked screen. Collapsing the two would make "who holds
    this?" unanswerable for anything that is not in perfect order.
    """

    AVAILABLE = "available"
    ASSIGNED = "assigned"
    RESERVED = "reserved"
    UNDER_MAINTENANCE = "under_maintenance"
    DAMAGED = "damaged"
    LOST = "lost"
    RETIRED = "retired"
    DISPOSED = "disposed"


ASSET_STATUS_SQL_VALUES = _sql_values(AssetStatus)

#: Statuses from which an asset can be handed to somebody. Deliberately narrow:
#: reserved is *not* here, because a reservation is a promise to a different
#: person and assigning over it is how two people end up expecting one laptop.
ASSIGNABLE_ASSET_STATUSES: frozenset[AssetStatus] = frozenset({AssetStatus.AVAILABLE})

#: End of life. Nothing transitions out of ``DISPOSED``, and an asset in either
#: state is excluded from the assignable inventory for good.
TERMINAL_ASSET_STATUSES: frozenset[AssetStatus] = frozenset({AssetStatus.RETIRED, AssetStatus.DISPOSED})

#: The permitted moves, as ``from -> {to}``. Enforced in
#: :meth:`AssetService._assert_transition`, which is the only place an asset's
#: status is allowed to change.
#:
#: Written as a table rather than a chain of ``if`` statements because the
#: interesting property is what is *absent*: there is no route from ``DISPOSED``
#: to anywhere, none from ``LOST`` to ``AVAILABLE`` without passing through a
#: recovery, and none that skips maintenance on the way back from damage.
ASSET_STATUS_TRANSITIONS: dict[AssetStatus, frozenset[AssetStatus]] = {
    AssetStatus.AVAILABLE: frozenset(
        {
            AssetStatus.ASSIGNED,
            AssetStatus.RESERVED,
            AssetStatus.UNDER_MAINTENANCE,
            AssetStatus.DAMAGED,
            AssetStatus.LOST,
            AssetStatus.RETIRED,
        }
    ),
    AssetStatus.ASSIGNED: frozenset(
        {
            AssetStatus.AVAILABLE,
            AssetStatus.UNDER_MAINTENANCE,
            AssetStatus.DAMAGED,
            AssetStatus.LOST,
        }
    ),
    AssetStatus.RESERVED: frozenset({AssetStatus.AVAILABLE, AssetStatus.ASSIGNED}),
    AssetStatus.UNDER_MAINTENANCE: frozenset(
        {
            AssetStatus.AVAILABLE,
            AssetStatus.DAMAGED,
            AssetStatus.RETIRED,
        }
    ),
    # Damage is repaired, written off, or the thing is retired. It never becomes
    # `available` in one step: something has to have been done to it first.
    AssetStatus.DAMAGED: frozenset({AssetStatus.UNDER_MAINTENANCE, AssetStatus.RETIRED}),
    # A recovered item goes to maintenance for inspection before it is offered
    # to anybody again.
    AssetStatus.LOST: frozenset({AssetStatus.UNDER_MAINTENANCE, AssetStatus.RETIRED}),
    AssetStatus.RETIRED: frozenset({AssetStatus.DISPOSED}),
    AssetStatus.DISPOSED: frozenset(),
}


class AssetCondition(StrEnum):
    """The physical state of the thing, recorded at every custody change."""

    NEW = "new"
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    DAMAGED = "damaged"


ASSET_CONDITION_SQL_VALUES = _sql_values(AssetCondition)


class MaintenanceStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


MAINTENANCE_STATUS_SQL_VALUES = _sql_values(MaintenanceStatus)


class MaintenanceType(StrEnum):
    PREVENTIVE = "preventive"
    REPAIR = "repair"
    UPGRADE = "upgrade"
    INSPECTION = "inspection"
    OTHER = "other"


MAINTENANCE_TYPE_SQL_VALUES = _sql_values(MaintenanceType)


class AssetEvent(StrEnum):
    """What a row of the asset history records.

    Append-only, like employment history: a correction is a new row. The
    history is the only complete account of where a thing has been, and it
    outlives the asset -- a disposed laptop still has to be explainable to an
    auditor two years later.
    """

    CREATED = "created"
    UPDATED = "updated"
    ASSIGNED = "assigned"
    RETURNED = "returned"
    TRANSFERRED = "transferred"
    MAINTENANCE_STARTED = "maintenance_started"
    MAINTENANCE_COMPLETED = "maintenance_completed"
    DAMAGED = "damaged"
    LOST = "lost"
    RECOVERED = "recovered"
    RETIRED = "retired"
    DISPOSED = "disposed"
    STATUS_CHANGED = "status_changed"
    CLEARANCE_WAIVED = "clearance_waived"


ASSET_EVENT_SQL_VALUES = _sql_values(AssetEvent)

#: How far ahead a warranty counts as "expiring soon" on the dashboard. Matches
#: the document vault's ``EXPIRY_WARNING_DAYS`` so the two never disagree about
#: what "soon" means.
WARRANTY_WARNING_DAYS = 30


# ----------------------------------------------------------------------
# Helpdesk
# ----------------------------------------------------------------------
class TicketStatus(StrEnum):
    """Where a request has got to.

    ``WAITING_ON_EMPLOYEE`` exists because the alternative is an agent's queue
    full of tickets that look like their work and are not. A request blocked on
    the person who raised it should stop counting against the team handling it,
    and should start again the moment they reply.

    ``REOPENED`` is distinct from ``OPEN`` for the same reason a correction is a
    new row elsewhere in this system: "resolved once, came back" is a fact worth
    keeping, and it is the number a service desk is actually judged on.
    """

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_ON_EMPLOYEE = "waiting_on_employee"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    REOPENED = "reopened"


TICKET_STATUS_SQL_VALUES = _sql_values(TicketStatus)

#: Statuses in which the ticket is still somebody's work.
OPEN_TICKET_STATUSES: frozenset[TicketStatus] = frozenset(
    {
        TicketStatus.OPEN,
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_ON_EMPLOYEE,
        TicketStatus.REOPENED,
    }
)

#: Nothing transitions out of these except a reopen, which only the requester or
#: an agent may do and only from ``RESOLVED``.
TERMINAL_TICKET_STATUSES: frozenset[TicketStatus] = frozenset({TicketStatus.CLOSED, TicketStatus.CANCELLED})

#: Permitted moves, ``from -> {to}``. Enforced in ``HelpdeskService``; see
#: ``ASSET_STATUS_TRANSITIONS`` for why this is a table rather than conditionals.
TICKET_STATUS_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.OPEN: frozenset(
        {
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_ON_EMPLOYEE,
            TicketStatus.RESOLVED,
            TicketStatus.CANCELLED,
        }
    ),
    TicketStatus.IN_PROGRESS: frozenset(
        {TicketStatus.WAITING_ON_EMPLOYEE, TicketStatus.RESOLVED, TicketStatus.CANCELLED}
    ),
    TicketStatus.WAITING_ON_EMPLOYEE: frozenset(
        {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CANCELLED}
    ),
    # A resolved ticket is closed by agreement or comes back. It does not go
    # straight back to "in progress" -- reopening is the event worth recording.
    TicketStatus.RESOLVED: frozenset({TicketStatus.CLOSED, TicketStatus.REOPENED}),
    TicketStatus.REOPENED: frozenset(
        {TicketStatus.IN_PROGRESS, TicketStatus.WAITING_ON_EMPLOYEE, TicketStatus.RESOLVED}
    ),
    TicketStatus.CLOSED: frozenset(),
    TicketStatus.CANCELLED: frozenset(),
}


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


TICKET_PRIORITY_SQL_VALUES = _sql_values(TicketPriority)

#: Hours to first response, by priority. A default, not a contract: every
#: category may override it, and nothing here escalates on its own -- the due
#: time exists so a queue can be sorted by what is late.
DEFAULT_SLA_HOURS: dict[TicketPriority, int] = {
    TicketPriority.URGENT: 4,
    TicketPriority.HIGH: 8,
    TicketPriority.MEDIUM: 24,
    TicketPriority.LOW: 72,
}


class TicketQueue(StrEnum):
    """Which desk a category routes to.

    Not a role and not a permission. The queue decides where a ticket appears
    and who is nominated to handle it; what a person may *do* to it is still
    decided by their permissions.
    """

    HR = "hr"
    IT = "it"
    ADMIN = "admin"
    FINANCE = "finance"
    FACILITIES = "facilities"


TICKET_QUEUE_SQL_VALUES = _sql_values(TicketQueue)


class TicketEvent(StrEnum):
    """Append-only history of one ticket."""

    RAISED = "raised"
    ASSIGNED = "assigned"
    STATUS_CHANGED = "status_changed"
    COMMENTED = "commented"
    PRIORITY_CHANGED = "priority_changed"
    CATEGORY_CHANGED = "category_changed"
    RESOLVED = "resolved"
    REOPENED = "reopened"
    CLOSED = "closed"


TICKET_EVENT_SQL_VALUES = _sql_values(TicketEvent)


# ----------------------------------------------------------------------
# Announcements
# ----------------------------------------------------------------------
class AnnouncementStatus(StrEnum):
    """Draft, scheduled, published, or taken down.

    ``SCHEDULED`` and ``PUBLISHED`` are separate states rather than one with a
    date in the future, because "is this visible now" is asked on every employee
    dashboard load and should be a column comparison, not a date calculation
    somebody has to remember to write correctly.
    """

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


ANNOUNCEMENT_STATUS_SQL_VALUES = _sql_values(AnnouncementStatus)


class AnnouncementAudience(StrEnum):
    """Who an announcement is for.

    Targeting is by organizational unit rather than by role: "everyone in
    Chennai" and "the engineering business unit" are the questions actually
    asked, and a role-based audience would send the canteen notice to whoever
    happens to hold ``leave:approve``.
    """

    ALL = "all"
    BUSINESS_UNIT = "business_unit"
    TEAM = "team"
    LOCATION = "location"


ANNOUNCEMENT_AUDIENCE_SQL_VALUES = _sql_values(AnnouncementAudience)


class AnnouncementPriority(StrEnum):
    NORMAL = "normal"
    IMPORTANT = "important"
    URGENT = "urgent"


ANNOUNCEMENT_PRIORITY_SQL_VALUES = _sql_values(AnnouncementPriority)


class PayFrequency(StrEnum):
    """How often a salary structure pays out.

    Phase 1 stores the schedule and calculates nothing against it. Monthly is
    the default because it is how this organization actually pays; weekly and
    biweekly exist so a structure created today does not need a migration when
    a contractor arrangement arrives.
    """

    MONTHLY = "monthly"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"


PAY_FREQUENCY_SQL_VALUES = _sql_values(PayFrequency)


class SalaryStructureStatus(StrEnum):
    """Lifecycle of a salary structure template.

    Distinct from :class:`RecordStatus` because a structure has a third state:
    ``draft`` is being written and cannot be assigned to anybody yet. Only an
    ``active`` structure may be assigned; an ``inactive`` one keeps resolving
    for the compensation records that already reference it.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


SALARY_STRUCTURE_STATUS_SQL_VALUES = _sql_values(SalaryStructureStatus)


class SalaryComponentType(StrEnum):
    """Whether a component adds to pay or subtracts from it."""

    EARNING = "earning"
    DEDUCTION = "deduction"


SALARY_COMPONENT_TYPE_SQL_VALUES = _sql_values(SalaryComponentType)


class SalaryCalculationType(StrEnum):
    """How a component's value is expressed.

    ``fixed`` is an amount of money; ``percentage`` is a rate against a base
    named by :class:`PercentageBasis`. Stored, never computed against in this
    phase — the payroll calculation that will read these belongs to a later one.
    """

    FIXED = "fixed"
    PERCENTAGE = "percentage"


SALARY_CALCULATION_TYPE_SQL_VALUES = _sql_values(SalaryCalculationType)


class PercentageBasis(StrEnum):
    """What a percentage component is a percentage *of*."""

    BASIC = "basic"
    GROSS = "gross"


PERCENTAGE_BASIS_SQL_VALUES = _sql_values(PercentageBasis)


class CompensationStatus(StrEnum):
    """Lifecycle of one employee compensation record.

    Two states only: a record is the current word on somebody's pay, or it has
    been ended by a revision. There is no ``deleted`` — salary history is
    append-only, and a correction is a new record ending the wrong one.
    """

    ACTIVE = "active"
    ENDED = "ended"


COMPENSATION_STATUS_SQL_VALUES = _sql_values(CompensationStatus)


class WorkingDaysRule(StrEnum):
    """How a payroll period counts the days somebody could have worked.

    Configuration only in this phase: the calculation engine that reads it is
    a later phase's. ``custom_working_days`` means the weekly-off list and the
    holiday calendar decide; the other two are the conventional shortcuts.
    """

    CALENDAR_DAYS = "calendar_days"
    WORKING_DAYS = "working_days"
    CUSTOM_WORKING_DAYS = "custom_working_days"


WORKING_DAYS_RULE_SQL_VALUES = _sql_values(WorkingDaysRule)


class PayrollDayBasis(StrEnum):
    """The denominator a per-day amount is computed against.

    One enum for proration, unpaid-leave deduction and leave rules, on
    purpose: they are the same question ("divide by what?") asked in three
    places, and three enums would eventually disagree.
    """

    CALENDAR_DAYS = "calendar_days"
    WORKING_DAYS = "working_days"


PAYROLL_DAY_BASIS_SQL_VALUES = _sql_values(PayrollDayBasis)


class UnpaidLeaveTreatment(StrEnum):
    """Whether unpaid leave reduces pay at all."""

    DEDUCT = "deduct"
    IGNORE = "ignore"


UNPAID_LEAVE_TREATMENT_SQL_VALUES = _sql_values(UnpaidLeaveTreatment)


class RoundingRule(StrEnum):
    """How the future calculation engine will round a computed amount.

    ``custom`` requires a precision (0.01, 1, 10, ...). Stored, never applied
    in this phase — existing salary records are exact and stay exact.
    """

    NONE = "none"
    NEAREST_WHOLE = "nearest_whole"
    NEAREST_HALF = "nearest_half"
    CUSTOM = "custom"


ROUNDING_RULE_SQL_VALUES = _sql_values(RoundingRule)


class PayrollPeriodStatus(StrEnum):
    """Lifecycle of one payroll period.

    This phase creates and manages periods; nothing here runs one. The
    transition table below is the only place the workflow is encoded, and the
    service consults it on every change — ``finalized`` and ``cancelled`` are
    terminal, and each review step can fall back exactly one step rather than
    jumping.
    """

    OPEN = "open"
    PROCESSING = "processing"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


PAYROLL_PERIOD_STATUS_SQL_VALUES = _sql_values(PayrollPeriodStatus)

#: Where a period may move next. Consulted by the service on every change.
PAYROLL_PERIOD_TRANSITIONS: dict[str, frozenset[str]] = {
    PayrollPeriodStatus.OPEN.value: frozenset(
        {PayrollPeriodStatus.PROCESSING.value, PayrollPeriodStatus.CANCELLED.value}
    ),
    PayrollPeriodStatus.PROCESSING.value: frozenset(
        {
            PayrollPeriodStatus.UNDER_REVIEW.value,
            PayrollPeriodStatus.OPEN.value,
            PayrollPeriodStatus.CANCELLED.value,
        }
    ),
    PayrollPeriodStatus.UNDER_REVIEW.value: frozenset(
        {
            PayrollPeriodStatus.APPROVED.value,
            PayrollPeriodStatus.PROCESSING.value,
            PayrollPeriodStatus.CANCELLED.value,
        }
    ),
    PayrollPeriodStatus.APPROVED.value: frozenset(
        {
            PayrollPeriodStatus.FINALIZED.value,
            PayrollPeriodStatus.UNDER_REVIEW.value,
            PayrollPeriodStatus.CANCELLED.value,
        }
    ),
    PayrollPeriodStatus.FINALIZED.value: frozenset(),
    PayrollPeriodStatus.CANCELLED.value: frozenset(),
}


class LeaveTreatment(StrEnum):
    """How one leave type behaves in payroll: paid keeps the salary whole,
    unpaid deducts against the configured day basis."""

    PAID = "paid"
    UNPAID = "unpaid"


LEAVE_TREATMENT_SQL_VALUES = _sql_values(LeaveTreatment)


class PayrollEligibility(StrEnum):
    """Whether an employee is in scope for payroll at all.

    Deliberately not derived from employment status alone: a contractor is an
    active employee the payroll run must skip, and a suspension is temporary
    in a way ``not_eligible`` is not.
    """

    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    SUSPENDED = "suspended"


PAYROLL_ELIGIBILITY_SQL_VALUES = _sql_values(PayrollEligibility)


class PayrollInputStatus(StrEnum):
    """State of one employee's payroll input for one period.

    ``ready`` means the data was gathered and nothing needs a human;
    ``requires_review`` means an exception was found or the source data
    changed after the snapshot; ``excluded`` means the employee is out of
    scope for the period — with the reason stated, never silently.
    """

    READY = "ready"
    REQUIRES_REVIEW = "requires_review"
    EXCLUDED = "excluded"


PAYROLL_INPUT_STATUS_SQL_VALUES = _sql_values(PayrollInputStatus)


class PayrollExceptionCategory(StrEnum):
    """Which sub-domain a payroll input exception came from."""

    ATTENDANCE = "attendance"
    LEAVE = "leave"
    OVERTIME = "overtime"
    COMPENSATION = "compensation"


PAYROLL_EXCEPTION_CATEGORY_SQL_VALUES = _sql_values(PayrollExceptionCategory)


class PayrollSourceType(StrEnum):
    """What kind of record a payroll input snapshot line points at."""

    ATTENDANCE = "attendance"
    REGULARIZATION = "regularization"
    LEAVE_REQUEST = "leave_request"


PAYROLL_SOURCE_TYPE_SQL_VALUES = _sql_values(PayrollSourceType)


class PayrollRunStatus(StrEnum):
    """Lifecycle of one payroll run.

    ``calculated`` doubles as "ready for review" and ``requires_review`` as
    "has exceptions"; ``in_review`` and ``review_complete`` are the Phase 5
    review workflow. Phase 6 adds the approval tail: ``pending_approval``
    (submitted, numbers frozen while an approver decides), ``returned``
    (sent back for correction — review and recalculation reopen), then
    ``approved`` and ``finalized``. Finalization is terminal: the run's
    records become read-only and the period locks.
    """

    DRAFT = "draft"
    CALCULATING = "calculating"
    REQUIRES_REVIEW = "requires_review"
    CALCULATED = "calculated"
    IN_REVIEW = "in_review"
    REVIEW_COMPLETE = "review_complete"
    PENDING_APPROVAL = "pending_approval"
    RETURNED = "returned"
    APPROVED = "approved"
    FINALIZED = "finalized"


PAYROLL_RUN_STATUS_SQL_VALUES = _sql_values(PayrollRunStatus)

#: Statuses in which a run's numbers may still be (re)computed. Everything
#: before submission — recalculating a run under review simply reopens it,
#: and a returned run is corrected the same way. From ``pending_approval``
#: on, the numbers an approver is looking at (or approved) cannot move.
RECALCULABLE_RUN_STATUSES: frozenset[str] = frozenset(
    {
        PayrollRunStatus.DRAFT.value,
        PayrollRunStatus.REQUIRES_REVIEW.value,
        PayrollRunStatus.CALCULATED.value,
        PayrollRunStatus.IN_REVIEW.value,
        PayrollRunStatus.REVIEW_COMPLETE.value,
        PayrollRunStatus.RETURNED.value,
    }
)

#: Statuses in which review acts (marks, adjustments, resolutions) are open.
#: ``returned`` is here on purpose: corrections after a send-back go through
#: the same review workflow, never around it.
REVIEWABLE_RUN_STATUSES: frozenset[str] = frozenset(
    {
        PayrollRunStatus.REQUIRES_REVIEW.value,
        PayrollRunStatus.CALCULATED.value,
        PayrollRunStatus.IN_REVIEW.value,
        PayrollRunStatus.REVIEW_COMPLETE.value,
        PayrollRunStatus.RETURNED.value,
    }
)

#: Statuses whose numbers are frozen: submitted, approved or finalized. Any
#: mutation attempt against a run in one of these is refused — and audited.
LOCKED_RUN_STATUSES: frozenset[str] = frozenset(
    {
        PayrollRunStatus.PENDING_APPROVAL.value,
        PayrollRunStatus.APPROVED.value,
        PayrollRunStatus.FINALIZED.value,
    }
)


class PayrollRecordStatus(StrEnum):
    """Outcome and review state of one employee's record within a run.

    The engine produces the first three; a human review moves ``calculated``
    to ``reviewed`` or ``adjustment_required``, and completing the run's
    review promotes accepted records to ``ready_for_approval``. Recalculation
    rebuilds the records, so review marks never survive a change of numbers.
    """

    CALCULATED = "calculated"
    REQUIRES_REVIEW = "requires_review"
    EXCLUDED = "excluded"
    REVIEWED = "reviewed"
    ADJUSTMENT_REQUIRED = "adjustment_required"
    READY_FOR_APPROVAL = "ready_for_approval"


PAYROLL_RECORD_STATUS_SQL_VALUES = _sql_values(PayrollRecordStatus)


class PayrollExceptionSeverity(StrEnum):
    """How much an exception matters to the run.

    ``critical`` blocks review completion (and, in the next phase, approval)
    until resolved or deliberately waived; the others inform.
    """

    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


PAYROLL_EXCEPTION_SEVERITY_SQL_VALUES = _sql_values(PayrollExceptionSeverity)


class PayrollRunExceptionType(StrEnum):
    """What kind of payroll-impacting issue a run exception describes."""

    MISSING_SALARY = "missing_salary"
    INVALID_COMPENSATION = "invalid_compensation"
    MISSING_ATTENDANCE = "missing_attendance"
    UNRESOLVED_CORRECTION = "unresolved_correction"
    UNAPPROVED_OVERTIME = "unapproved_overtime"
    INVALID_LEAVE = "invalid_leave"
    NEGATIVE_LEAVE_BALANCE = "negative_leave_balance"
    INVALID_COMPONENT = "invalid_component"
    CALCULATION_MISMATCH = "calculation_mismatch"
    MISSING_INPUT = "missing_input"
    OTHER = "other"


PAYROLL_RUN_EXCEPTION_TYPE_SQL_VALUES = _sql_values(PayrollRunExceptionType)


class PayrollExceptionStatus(StrEnum):
    """Open until a human resolves it — resolving includes a deliberate
    waive; deleting is not a state."""

    OPEN = "open"
    RESOLVED = "resolved"


PAYROLL_EXCEPTION_STATUS_SQL_VALUES = _sql_values(PayrollExceptionStatus)


class PayrollAdjustmentStatus(StrEnum):
    """An adjustment is cancelled, never deleted: the history must keep
    saying what was added and then taken back."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


PAYROLL_ADJUSTMENT_STATUS_SQL_VALUES = _sql_values(PayrollAdjustmentStatus)


class PayrollApprovalAction(StrEnum):
    """One step of the approval trail (Phase 6). Append-only: each submit,
    approval, send-back and finalization is its own row with its own actor,
    comment and the totals as they stood at that moment."""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    RETURNED = "returned"
    FINALIZED = "finalized"


PAYROLL_APPROVAL_ACTION_SQL_VALUES = _sql_values(PayrollApprovalAction)


class PayslipStatus(StrEnum):
    """A payslip exists or it does not (Phase 7). Regeneration replaces the
    document file only and is tracked by timestamp, not by status; the
    figures never change because the finalized snapshot never changes."""

    GENERATED = "generated"


PAYSLIP_STATUS_SQL_VALUES = _sql_values(PayslipStatus)


class FinalSettlementStatus(StrEnum):
    """Full & final settlement workflow (Phase 8). ``settled`` is terminal:
    the settlement becomes read-only and its snapshot is the record."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    SETTLED = "settled"


FINAL_SETTLEMENT_STATUS_SQL_VALUES = _sql_values(FinalSettlementStatus)

#: Statuses in which the settlement's figures may still change.
EDITABLE_SETTLEMENT_STATUSES: frozenset[str] = frozenset(
    {FinalSettlementStatus.DRAFT.value, FinalSettlementStatus.UNDER_REVIEW.value}
)


class SettlementAdjustmentType(StrEnum):
    """What an F&F adjustment is. The direction (earning or deduction)
    follows from the type, so a "recovery" can never accidentally pay out."""

    FINAL_BONUS = "final_bonus"
    INCENTIVE = "incentive"
    LEAVE_ENCASHMENT = "leave_encashment"
    OTHER_EARNING = "other_earning"
    RECOVERY = "recovery"
    ASSET_RECOVERY = "asset_recovery"
    OTHER_DEDUCTION = "other_deduction"


SETTLEMENT_ADJUSTMENT_TYPE_SQL_VALUES = _sql_values(SettlementAdjustmentType)

#: Adjustment types that add to the settlement; everything else deducts.
SETTLEMENT_EARNING_TYPES: frozenset[str] = frozenset(
    {
        SettlementAdjustmentType.FINAL_BONUS.value,
        SettlementAdjustmentType.INCENTIVE.value,
        SettlementAdjustmentType.LEAVE_ENCASHMENT.value,
        SettlementAdjustmentType.OTHER_EARNING.value,
    }
)


class SettlementAdjustmentStatus(StrEnum):
    """Pending until an approver decides. Only approved adjustments count;
    rejected ones stay on record with the decision."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


SETTLEMENT_ADJUSTMENT_STATUS_SQL_VALUES = _sql_values(SettlementAdjustmentStatus)


class SettlementItemCategory(StrEnum):
    """The four components a settlement is stored as — never one number."""

    EARNING = "earning"
    ENCASHMENT = "encashment"
    ADJUSTMENT = "adjustment"
    DEDUCTION = "deduction"


SETTLEMENT_ITEM_CATEGORY_SQL_VALUES = _sql_values(SettlementItemCategory)


#: The review checklist every run carries, as (key, label). A code constant
#: rather than rows invented per run, so the gate in review completion and
#: the screen always agree on what "all items" means.
DEFAULT_REVIEW_CHECKLIST: tuple[tuple[str, str], ...] = (
    ("salaries_valid", "All employees have valid salary"),
    ("attendance_reviewed", "Attendance inputs reviewed"),
    ("leave_reviewed", "Leave inputs reviewed"),
    ("overtime_reviewed", "Overtime reviewed"),
    ("exceptions_reviewed", "Exceptions reviewed"),
    ("adjustments_reviewed", "Adjustments reviewed"),
    ("gross_reviewed", "Gross payroll reviewed"),
    ("deductions_reviewed", "Deductions reviewed"),
    ("net_reviewed", "Net payroll reviewed"),
)


class PayrollItemType(StrEnum):
    """Whether a payroll line adds to pay or subtracts from it."""

    EARNING = "earning"
    DEDUCTION = "deduction"


PAYROLL_ITEM_TYPE_SQL_VALUES = _sql_values(PayrollItemType)


class PayrollLineSource(StrEnum):
    """Where a payroll line came from."""

    COMPONENT = "component"
    OVERTIME = "overtime"
    UNPAID_LEAVE = "unpaid_leave"


PAYROLL_LINE_SOURCE_SQL_VALUES = _sql_values(PayrollLineSource)


class PayrollEligibilityReason(StrEnum):
    """Why an employee holds their eligibility state."""

    ACTIVE_EMPLOYEE = "active_employee"
    EXITED_EMPLOYEE = "exited_employee"
    CONTRACTOR = "contractor"
    PAYROLL_EXCLUDED = "payroll_excluded"
    PENDING_ONBOARDING = "pending_onboarding"


PAYROLL_ELIGIBILITY_REASON_SQL_VALUES = _sql_values(PayrollEligibilityReason)


#: The fallback used only when neither the employment type nor an explicit
#: adjustment says otherwise. Deliberately a named constant rather than a
#: literal at a call site: `OffboardingService._resolve_notice_days` is the one
#: place that reads it, and the value it falls back to should be visible.
DEFAULT_NOTICE_PERIOD_DAYS = 30

#: The longest a person can plausibly have worked in one day. Anything beyond it
#: is a typo, and letting it through corrupts every utilisation figure downstream.
MAX_DAILY_HOURS = 24

#: Utilisation at or above this is flagged; matches the allocation module so the
#: two never disagree about what "near capacity" means.
LATE_ARRIVAL_GRACE_MINUTES = 0
