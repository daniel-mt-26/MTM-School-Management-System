Absolutely. Below is a clean **copy-and-paste version** of the updated `README.md`, based on your existing README structure and incorporating the newer MTM functionality.

````markdown
# MTM School Management System

## Overview

The MTM School Management System is a multi-school web application designed to manage the daily administrative, academic, student, parent, communication, and financial operations of schools from one platform.

The system is designed as a **multi-school platform**, where each school operates as a separate tenant with its own private data.

MTM currently supports three main user roles:

1. **MTM Platform Administrator**
2. **School Administrator / Receptionist**
3. **Parent / Guardian**

Students do not have separate login accounts.

The Django backend is the authoritative application layer and is responsible for authentication, permissions, tenant isolation, financial calculations, academic rules, and access control.

---

# Multi-School Structure

The same MTM application can be used by multiple schools.

```text
MTM PLATFORM
│
├── School A
│   └── Private school data
│
├── School B
│   └── Private school data
│
└── School C
    └── Private school data
````

Each school is isolated from every other school.

A School A administrator cannot access School B's:

* Students
* Parents
* Classes
* Academic records
* Homework
* Fees
* Payments
* Receipts
* Financial ledgers
* Expenses
* Communication records
* Other private school information

Tenant separation is enforced by the Django backend rather than simply hiding data in the React frontend.

For a school administrator, the school is determined through:

```text
Authenticated User
        ↓
School Administrator
        ↓
School
```

The frontend does not determine tenant ownership.

The client does not need to submit a `school_id` when creating normal school-owned records.

---

# MTM Platform Administrator

The MTM Platform Administrator manages the MTM platform rather than operating individual schools.

The Platform Administrator may manage:

* School accounts
* School registration
* Platform settings
* System configuration
* System status
* Subscription information
* Technical administration

The Platform Administrator does not automatically have access to private school records such as:

* Student personal information
* Parent information
* Student financial information
* Fee records
* Payment history
* School expenses
* Academic results
* Homework
* Report cards
* Private school documents
* Communication history

Any future support access to private school information should be separately controlled, authorised, and audited.

---

# School Administrator / Receptionist

Each School Administrator is associated with one school.

When the administrator logs in, the backend automatically determines which school the account belongs to.

The administrator does not manually choose a school when creating or managing records.

School Administrators can manage their school's:

* Students
* Parents
* Classes
* Academic years
* Terms
* Subjects
* Enrolments
* Timetables
* Homework
* Results
* Report cards
* Fees
* Recurring fees
* Fee assignments
* Payments
* Receipts
* Student financial ledgers
* School expenses
* Daily cashbook
* Communication
* Notifications
* Audit history
* School settings

---

# Authentication

MTM uses JWT authentication.

Main authentication endpoints include:

```text
POST /api/auth/token/
POST /api/auth/token/refresh/
GET  /api/auth/me/
```

The authenticated user determines their role and authorised access.

Supported roles:

```text
platform_admin
school_admin
parent
```

---

# Authentication and Permissions

The system uses role-based permissions.

| Function                  | MTM Platform Admin          | School Admin               | Parent                              |
| ------------------------- | --------------------------- | -------------------------- | ----------------------------------- |
| Platform management       | Full access                 | No access                  | No access                           |
| School account management | Platform level              | Own school where permitted | No access                           |
| Student management        | No automatic private access | Own school                 | Own children read-only              |
| Parent management         | No automatic private access | Own school                 | Own account                         |
| Class management          | No automatic private access | Own school                 | View child's class                  |
| Homework management       | No automatic private access | Own school                 | Published homework for own children |
| Fee management            | No automatic private access | Own school                 | View own children                   |
| Payments                  | No automatic private access | Own school                 | View own children                   |
| Receipts                  | No automatic private access | Own school                 | Own children                        |
| Student ledger            | No automatic private access | Own school                 | Own children                        |
| School expenses           | No automatic private access | Own school                 | No access                           |
| Daily cashbook            | No automatic private access | Own school                 | No access                           |
| Academic results          | No automatic private access | Own school                 | Own children                        |
| Report cards              | No automatic private access | Own school                 | Own children                        |
| Communication             | No automatic private access | Own school                 | Own notifications/preferences       |
| Audit history             | No automatic private access | Own school                 | No access                           |

Parents must only be able to access children linked to their account.

School administrators must only be able to access records belonging to their school.

---

# Administrator Dashboard

The School Administrator Dashboard provides access to the main areas of the system.

Main sections:

```text
Dashboard
│
├── Students
├── Parents
├── Academics
├── Finance
├── Communication
└── Settings
```

The dashboard displays the school's:

* Name
* Logo
* Main navigation
* Search
* Logout control

The dashboard search currently searches:

* Students
* Parents

Selecting a student search result opens that student's profile directly.

Selecting a parent search result opens that parent's profile directly.

Class search is intentionally excluded from the dashboard search because classes are managed under Academics.

---

# Student Management

School Administrators can:

* Register students
* Edit student information
* View student profiles
* Search for students
* Filter students by class
* Filter students by active status
* Assign students to classes
* Move students between classes
* Maintain enrolment history
* Link parents and guardians
* View financial information
* View academic information

Students belong explicitly to a school.

Admission numbers are unique within each school rather than globally.

For example:

```text
School A
Admission Number: 001

School B
Admission Number: 001
```

Both are valid because they belong to different schools.

---

# Searchable Student Selection

Where the system requires an administrator to choose a student, MTM uses searchable student selection rather than relying on large dropdown lists.

Search can support:

* First name
* Last name
* Full name
* Admission number

Example:

```text
Search Student

Daniel

Daniel Grey
ADM-001
Grade 4A
```

Where a Class filter is available, selecting a class restricts student search results to students currently in that class.

Example:

```text
Class:
Grade 4A

Search:
Daniel

Result:
Daniel Grey — ADM-001 — Grade 4A
```

This is used in areas such as:

* Payments
* Parent-child linking
* Academic records
* Finance records
* Other student-specific workflows

---

# Student Enrolment History

MTM preserves student enrolment history.

A student's previous class is not overwritten when they transfer.

Example:

```text
Daniel Grey

Grade 3A
13 January 2026 → 11 May 2026

Grade 3B
12 May 2026 → Current
```

The transfer system supports an effective transfer date.

The system prevents:

* Multiple active enrolments
* Invalid overlapping enrolments
* Transfers into another school's class

---

# Parent Management

Parents and guardians have secure MTM accounts.

One parent can be linked to multiple students.

One student may also be linked to multiple parents or guardians.

Example:

```text
Michael Grey
│
├── Daniel Grey
└── Ava Grey
```

School Administrators can:

* Create parent accounts
* Search parents
* View parent profiles
* Edit parent information
* Link children
* Unlink children where permitted
* Record relationships
* Identify primary contacts

When linking a child, the administrator searches for the child instead of using a long student dropdown.

Example:

```text
Search Child

Daniel

Daniel Grey — ADM-001 — Grade 4A
```

Already linked students can be excluded from available search results.

---

# Parent Portal

Parents have their own secure portal.

The Parent Portal only displays information belonging to students linked to the logged-in parent account.

A parent may have multiple children.

Example:

```text
Parent: Michael Grey

Children:

Daniel Grey
Grade 4A

Ava Grey
Grade 2A
```

Parents can access:

* Student profile information
* Current class
* Homework
* Timetable
* Fees
* Outstanding balances
* Payment history
* Receipts
* Academic results
* Report cards
* Notifications
* Communication settings

The Parent Portal includes Logout.

Parents cannot modify school academic, administrative, or financial records.

---

# Class Management

Each school can create its own classes.

Examples:

```text
ECDA
ECDB
Grade 1A
Grade 1B
Grade 2A
Grade 2B
Grade 3A
Grade 4A
Grade 5A
Grade 6A
Grade 7A
```

Different schools may use identical class names.

For example:

```text
School A
└── Grade 4A

School B
└── Grade 4A
```

These are different database records because each class belongs to a different school.

Class names are unique within an individual school.

---

# Academic Years

An Academic Year represents the complete school year.

Example:

```text
2026
```

Academic Years are used to separate historical school information across years.

For example:

```text
2026
2027
2028
```

Academic Years are used in:

* Enrolments
* Terms
* Timetables
* Results
* Report cards
* Fees
* Homework
* Financial reporting

---

# Terms

Terms represent subdivisions of an Academic Year.

Example:

```text
2026
│
├── Term 1
├── Term 2
└── Term 3
```

Academic Year and Term are intentionally separate.

This allows MTM to distinguish between:

```text
2026 → Term 1
2027 → Term 1
```

even though both Terms are called `Term 1`.

Where an Academic Year selector is already visible, the Term dropdown displays:

```text
Term 1
Term 2
Term 3
```

rather than unnecessarily repeating:

```text
2026 Term 1
2026 Term 2
2026 Term 3
```

---

# Subjects

School Administrators can:

* Create subjects
* Edit subjects
* Assign subjects to classes

Subjects remain school scoped.

A class-subject relationship must belong to the same school.

---

# Class Timetable

MTM uses class-based timetables.

Individual students do not have separate duplicated timetables.

The structure is:

```text
Student
    ↓
Current Class
    ↓
Class Timetable
```

For example:

```text
Grade 4A
Academic Year: 2026
Term: Term 2
```

Every student in Grade 4A uses that timetable.

Timetable entries may contain:

* Day
* Start time
* End time
* Subject

Timetables can also contain non-subject activities such as:

* Break
* Lunch
* Assembly

MTM prevents overlapping timetable periods within the same class, Academic Year, Term, and day.

Parents can view their child's class timetable.

---

# Homework

Homework is part of the Academics module.

School Administrators can:

* Create homework
* Edit homework
* Save homework as Draft
* Publish homework
* Delete homework where permitted
* Filter homework
* Add instructions
* Select a class
* Select an optional subject
* Set assigned dates
* Set due dates
* Upload files
* Upload images

Homework supports:

```text
Draft
Published
```

Draft Homework is not visible to parents.

Published Homework can be viewed by authorised parents.

---

# Homework Attachments

Administrators may attach files to Homework.

Supported formats:

```text
PDF
DOCX
JPG
JPEG
PNG
```

Limits:

```text
Maximum files per Homework: 5
Maximum size per file: 10 MB
```

The backend validates the actual file contents rather than relying only on the filename extension.

Homework attachments are protected.

Direct public access to:

```text
/media/homework/...
```

is blocked.

Files are downloaded through authenticated endpoints.

---

# Homework Parent Access

Parents have read-only Homework access.

Parent access is validated using:

* Logged-in parent
* Parent-child relationship
* Student school
* Current class
* Historical enrolment where relevant
* Homework publication status

Parents cannot access:

* Draft homework
* Homework from unrelated students
* Homework belonging to another school

---

# Homework Attachment Retention

Homework attachments expire automatically.

Default retention timezone:

```text
Africa/Johannesburg
```

Expiry rules:

```text
Monday upload
→ expires after 24 hours

Tuesday upload
→ expires after 24 hours

Wednesday upload
→ expires after 24 hours

Thursday upload
→ expires after 24 hours

Friday upload
→ expires Monday at 08:00

Saturday upload
→ expires Monday at 08:00

Sunday upload
→ expires Monday at 08:00
```

Expired attachments are no longer available for download.

Physical expired files and attachment database records can be removed using:

```bash
python manage.py purge_expired_homework_attachments
```

In production this command should be scheduled regularly, for example once every hour.

---

# Academic Results

School Administrators can:

* Enter results
* Edit results
* View results
* Store results by subject
* Store results by term
* Store results by Academic Year
* Maintain historical results

Parents can view academic results belonging to their linked children.

The backend validates all relationships to ensure that:

* Student
* Subject
* Class
* Term
* Academic Year

belong to the authorised school.

---

# Report Cards

MTM supports student report cards.

Report cards are associated with:

* Student
* Academic Year
* Term

Historical report cards are retained.

Parents can view report cards for their own linked children.

Report card availability may also trigger parent notifications.

---

# Future Academic Feature

MTM may later support withholding results or report cards when school fees remain unpaid.

This would be based on the individual school's policy.

This is not currently a core rule.

---

# Finance

MTM Finance handles two major areas:

1. Student billing
2. School operational finances

Finance navigation includes:

```text
Finance
│
├── Fees
├── Recurring Fees
├── Fee Assignments
├── Payments
├── Receipts
├── Student Balances
├── Ledger
├── Expenses
├── Daily Cashbook
└── Reports
```

Financial calculations are performed by Django.

React displays backend-calculated values rather than acting as the authoritative financial calculator.

---

# School Currency

Each school has an operational currency.

Examples:

```text
USD
ZAR
ZWL
```

Currency information is stored with financial records where required.

The backend protects historical financial information from unsafe currency changes.

---

# Fee Management

School Administrators can:

* Create fees
* Edit fees
* Associate fees with classes
* Associate fees with terms
* Associate fees with Academic Years
* Assign fees to students
* Assign fees to classes
* Track outstanding balances

Example:

```text
Term 2 Tuition

Charge:
USD 300.00
```

---

# Fee Assignments

A Fee Assignment represents a fee or charge that has been assigned to a specific student.

Example:

```text
Fee:
Term 2 Tuition

Student:
Daniel Grey

Charge:
USD 300.00
```

When recording payments, the user-facing interface refers to this as:

```text
Fee / Charge
```

rather than exposing the technical database term `Fee Assignment`.

---

# Recurring Monthly Fees

MTM supports recurring monthly fees.

There are two separate concepts.

## Recurring Fee Setup

This defines the repeating rule.

Example:

```text
Monthly Tuition

Amount:
USD 100.00

Class:
Grade 4A

Start Month:
January 2026

End Month:
November 2026
```

The setup tells MTM what fee should repeat.

## Generate Monthly Charges

The monthly generation process creates the actual student charges for a selected month.

Example:

```text
Recurring Fee Setup
        ↓
Generate February 2026
        ↓
February charges created
```

Monthly fee generation is idempotent.

Running the generator twice for the same month does not create duplicate charges.

Django remains the source of truth for recurring financial obligations.

---

# Payments

School Administrators can record payments towards student charges.

MTM supports:

* Full payments
* Partial payments
* Backdated payments
* Payment methods
* Payment references
* Automatic receipt creation
* Ledger entries
* Outstanding balance calculation
* Overpayment protection

Example:

```text
Student:
Daniel Grey

Charge:
USD 300.00

Payment:
USD 100.00

Outstanding:
USD 200.00
```

The payment date represents when the payment actually happened.

The database creation timestamp represents when the transaction was entered into MTM.

These dates may be different when historical transactions are entered.

---

# Payment Reversals

Financial history should not be silently rewritten.

Payments therefore support reversal instead of ordinary deletion.

A Payment Reversal:

* Preserves the original payment
* Preserves the original receipt
* Requires a reason
* Records the administrator
* Records the reversal date/time
* Creates the necessary compensating financial entry
* Restores the correct balance

This creates a reliable audit trail.

---

# Student Financial Ledger

Each student has an individual financial ledger.

The ledger records:

* Charges
* Payments
* Reversals
* Running balances

Example:

| Date   | Description    |      Debit |     Credit |    Balance |
| ------ | -------------- | ---------: | ---------: | ---------: |
| 01 May | Term 2 Tuition | USD 300.00 |            | USD 300.00 |
| 10 May | Payment        |            | USD 100.00 | USD 200.00 |
| 15 May | Sports Fee     |  USD 50.00 |            | USD 250.00 |
| 20 May | Payment        |            |  USD 50.00 | USD 200.00 |

The backend calculates ledger totals.

Ledger totals include:

```text
Total Charges
Total Payments
Closing Balance
```

The Student Financial Ledger explains how the student's current financial position was reached.

---

# Receipts

Successful payments generate unique receipts.

Receipts are school branded.

Generated PDF receipts may contain:

* School logo
* School name
* School address
* School phone
* School email
* Receipt number
* Payment date
* Student name
* Admission number
* Class
* Fee / Charge
* Amount paid
* Currency
* Payment method
* Reference
* Recorded date
* Outstanding balance

If a payment has been reversed, the receipt clearly displays:

```text
REVERSED
```

Receipt PDFs are protected.

School Administrators may only access receipts belonging to their school.

Parents may only access receipts belonging to their linked children.

---

# School Expenses

MTM records the operational expenses of the school.

School expenses are separate from student fees.

A student Fee is money the student owes the school.

An Expense is money the school spends.

Examples of school expenses include:

* Food
* Utilities
* Transport
* Salaries
* Maintenance
* Stationery
* Rent
* Equipment
* Other operating expenses

An Expense record can contain:

```text
Expense Date
Category
Description
Amount
Currency
Payment Method
Reference
Notes
Recorded By
Created At
```

Example:

```text
Date:
14 August 2026

Category:
Stationery

Description:
Printer paper and exercise books

Amount:
USD 75.00

Payment Method:
Cash
```

Expense ownership is determined by the authenticated School Administrator's school.

The frontend does not provide a `school_id` as tenant authority.

School A cannot access School B's expenses.

Parents cannot access school operational expenses.

Expense records are preserved as financial history instead of being casually hard deleted.

---

# Daily Cashbook / Daily Ledger

The Daily Cashbook provides a daily summary of money coming into and leaving the school.

The Daily Cashbook is different from the Student Financial Ledger.

The Student Financial Ledger answers:

```text
Why does this student owe this amount?
```

The Daily Cashbook answers:

```text
How much money came into the school today?

How much money did the school spend today?

What is today's net cash movement?
```

The Daily Cashbook counts actual money received.

A fee being charged does not automatically count as income.

For example:

```text
Student fees charged today:
USD 5,000

Actual payments received today:
USD 1,200
```

The Daily Cashbook Income is:

```text
USD 1,200
```

not:

```text
USD 5,000
```

The calculation is:

```text
Total Income
=
Valid non-reversed payments received

Total Expenses
=
School expenses recorded for the date

Net Cash Movement
=
Total Income - Total Expenses
```

Example:

```text
14 August 2026

INCOME

Student Payments
USD 850.00


EXPENSES

Food
USD 120.00

Transport
USD 60.00

Stationery
USD 40.00


Total Expenses
USD 220.00


NET CASH MOVEMENT

USD 630.00
```

This provides the school with a simple daily operational financial record.

Daily Cashbook calculations are performed by Django.

The Daily Cashbook is tenant scoped.

School A cannot view School B's Daily Cashbook.

Parents cannot view the school's operational Daily Cashbook.

---

# Finance Reports

MTM Finance can provide information such as:

* Student balances
* Outstanding fee balances
* Payment history
* Financial ledger history
* Receipt history
* School expense history
* Daily income
* Daily expenses
* Daily net cash movement
* Individual student statements
* Financial filtering by date
* Financial filtering by student
* Financial filtering by class where implemented

More advanced accounting reports may be added later.

---

# Parent Finance Access

Parents have read-only financial access for linked children.

Parents can view:

* Student charges
* Outstanding balances
* Payment history
* Financial history
* Receipts
* Receipt PDFs
* Reversal status

Parents cannot:

* Create fees
* Assign fees
* Record payments
* Reverse payments
* Edit financial ledger entries
* Create expenses
* View school operational expenses
* View the Daily Cashbook

---

# Communication

MTM includes a communication system for schools and parents.

Communication features include:

* In-app notifications
* School announcements
* Communication history
* Parent WhatsApp preferences
* Payment receipt notifications
* Fee reminders
* Report card notifications
* Delivery status tracking

Django remains the source of truth.

---

# School Announcements

School Administrators can create announcements.

Announcements may target:

* All parents
* A class
* A student
* A parent

The backend determines the valid recipients.

Sent announcement history is retained.

---

# Parent WhatsApp Preferences

Parents can manage WhatsApp communication preferences.

The system supports:

* Opt-in
* Opt-out
* Phone number validation
* Communication preferences

Possessing a parent's phone number does not automatically mean the parent has consented to WhatsApp communication.

If a parent opts out, new WhatsApp delivery jobs are not created for that parent.

---

# Communication Outbox

MTM uses a durable communication outbox.

Communication records may include:

* Parent
* Student context
* Channel
* Event type
* Template
* Status
* Provider message ID
* Idempotency key
* Attempts
* Created time
* Sent time
* Delivered time
* Read time
* Failure information

Possible statuses include:

```text
Pending
Processing
Sent
Delivered
Read
Failed
Cancelled
```

Communication generation is idempotent to help prevent duplicate messages.

---

# n8n Integration

n8n is used as the automation and communication delivery layer.

The architecture is:

```text
MTM Django
    ↓
Communication Outbox
    ↓
n8n
    ↓
WhatsApp Business Cloud
    ↓
Parent
```

n8n can:

* Claim communication jobs
* Send WhatsApp templates
* Retrieve protected receipt attachments
* Report successful sends
* Report failures
* Receive delivery updates
* Receive read updates
* Return status updates to MTM

n8n does not:

* Calculate student balances
* Create fees
* Calculate charges
* Determine school ownership
* Determine parent-child relationships

Django remains authoritative.

Live WhatsApp activation requires real Meta Business and n8n production configuration.

---

# Notifications

Parents can receive notifications about:

* New fees
* Payments
* Receipts
* Outstanding balances
* Academic results
* Report cards
* Homework
* School announcements

Notifications may be delivered through:

* Parent Portal
* WhatsApp where configured
* Other future channels

---

# Audit Trail

MTM includes an append-only Audit Log.

Important school actions can be recorded.

Examples include:

* School setting changes
* Student creation
* Student updates
* Student transfers
* Parent creation
* Parent updates
* Parent-child links
* Fee creation
* Fee assignment
* Payment recording
* Payment reversal
* Result creation
* Result updates
* Report card notifications
* Announcement sending

Audit logs are tenant scoped.

School Administrators only see audit records belonging to their school.

Sensitive information is not stored in audit logs.

This includes:

* Passwords
* JWT tokens
* Django secrets
* Database passwords
* n8n secrets
* Meta access tokens

---

# Demo School

MTM contains fictional demo data for development and presentations.

Example demo school:

```text
Sunrise Primary School
```

Demo data includes:

* School Administrator
* Realistic fictional student names
* Realistic fictional parent names
* Parent-child relationships
* Classes
* Subjects
* Academic Year
* Terms
* Enrolments
* Timetables
* Fees
* Recurring charges
* Fee assignments
* Payments
* Receipts
* Results
* Report cards
* Notifications
* Announcements
* School expenses

A dedicated demo parent account is linked to multiple children so the Parent Portal can be demonstrated.

Demo passwords are not hardcoded into source control.

---

# Demo Commands

Create the demo school:

```bash
python manage.py create_demo_school
```

Reset the demo school:

```bash
python manage.py reset_demo_school --yes
```

Demo credentials can be provided through command options or environment configuration.

Secrets should never be committed to Git.

---

# Homework Cleanup Command

Expired Homework files can be permanently removed using:

```bash
python manage.py purge_expired_homework_attachments
```

In production, this should be scheduled regularly.

For example:

```text
Once every hour
```

---

# Recurring Fee Command

Recurring monthly charges can also be generated using the Django management command:

```bash
python manage.py generate_recurring_fees --month YYYY-MM-DD
```

Example:

```bash
python manage.py generate_recurring_fees --month 2026-08-01
```

The recurring fee generator is designed to avoid duplicate monthly charges.

---

# Health Checks

MTM includes health endpoints for deployment monitoring.

```text
GET /api/health/
GET /api/health/ready/
```

These endpoints should not expose:

* Passwords
* Database credentials
* School private data
* API secrets

---

# Security Principles

MTM follows several important security rules.

## Tenant Isolation

School ownership is determined by the authenticated backend user.

The frontend does not decide school ownership.

## Parent Isolation

Parents can only access children linked to their Parent account.

## Password Security

Passwords are hashed using Django's password system.

Plaintext passwords are never stored.

## Environment Secrets

Sensitive configuration belongs in environment variables.

Examples:

```text
DJANGO_SECRET_KEY
DATABASE_PASSWORD
MTM_DEMO_ADMIN_PASSWORD
MTM_DEMO_PARENT_PASSWORD
N8N_INTEGRATION_SECRET
META_ACCESS_TOKEN
```

These should never be committed to Git.

## Financial Integrity

Financial transactions use backend validation and database transactions where appropriate.

Payment reversals preserve historical information.

## Protected Files

Protected documents such as:

* Homework attachments
* Receipt PDFs

must be served through authorised endpoints rather than becoming public files.

---

# PostgreSQL and Supabase

MTM uses PostgreSQL as its relational database.

Supabase may be used as a managed PostgreSQL hosting provider.

The intended architecture remains:

```text
React Frontend
      ↓
Django REST API
      ↓
PostgreSQL / Supabase
```

React should not directly access MTM's private school database tables.

Django remains responsible for:

* Authentication
* Tenant isolation
* Permissions
* Business logic
* Financial calculations
* Parent-child access
* Academic rules

PostgreSQL Row Level Security may later be added as an additional defence-in-depth security layer.

RLS should be deliberately designed and tested rather than automatically enabled without matching policies.

RLS does not replace Django permissions.

---

# Technology Stack

## Frontend

* React
* Vite
* JavaScript
* HTML
* CSS

## Backend

* Python
* Django
* Django REST Framework
* SimpleJWT

## Database

* PostgreSQL
* Supabase PostgreSQL may be used for hosted deployment

## Communication / Automation

* n8n
* WhatsApp Business Cloud architecture

## Development Tools

* Visual Studio Code
* Git
* GitHub

---

# Production Configuration

Production configuration is environment based.

Configuration includes:

* Django secret key
* Debug mode
* Allowed hosts
* CORS
* CSRF trusted origins
* Database configuration
* JWT settings
* HTTPS settings
* Secure cookies
* Proxy configuration
* Logging
* n8n integration
* Homework retention timezone

Production should use:

```text
DEBUG=False
```

Real credentials must never be committed to the Git repository.

---

# Static and Media Files

During local development, Django may serve media while:

```text
DEBUG=True
```

Production should use an appropriate media and static file strategy.

Protected files must remain protected even when using external storage.

This is particularly important for:

* Homework attachments
* Receipts
* School documents
* Other private records

---

# Backup and Restore

Production deployment should include backup procedures.

Backups should include:

* PostgreSQL database
* School logos
* Required media files
* Protected application media

Database restores should be tested in an isolated environment.

A restore procedure should be verified before MTM is considered production ready.

---

# Current Migration History

Current core migration history includes:

```text
0001  Initial schema

0002  School logo

0003  Student enrolment history constraints

0004  Student school ownership and
      school-specific admission numbers

0005  Parent school ownership

0006  Class timetable

0007  Finance hardening,
      currency,
      recurring fees

0008  Communication outbox

0009  Audit logging
      and demo tenant

0010  School expenses

0011  Homework
      and Homework attachments

0012  Homework attachment expiry
```

Migration status should be checked using:

```bash
python manage.py showmigrations core
```

---

# Important Django Commands

## Start Django Server

```bash
python manage.py runserver
```

## Apply Migrations

```bash
python manage.py migrate
```

## View Migration Status

```bash
python manage.py showmigrations core
```

## Django System Check

```bash
python manage.py check
```

## Run Tests

```bash
python manage.py test core.tests -v 2
```

## Generate Monthly Fees

```bash
python manage.py generate_recurring_fees --month YYYY-MM-DD
```

## Purge Expired Homework Attachments

```bash
python manage.py purge_expired_homework_attachments
```

## Create Demo School

```bash
python manage.py create_demo_school
```

## Reset Demo School

```bash
python manage.py reset_demo_school --yes
```

---

# Development Status

Major implemented functionality includes:

* React frontend
* Django backend
* PostgreSQL database
* JWT authentication
* Multi-school tenant architecture
* Platform Administrator role
* School Administrator role
* Parent role
* Student Management
* Parent Management
* Searchable student selection
* Student profiles
* Parent profiles
* Parent-child linking
* Academic Years
* Terms
* Classes
* Subjects
* Student enrolment history
* Class transfers
* Class timetables
* Academic results
* Report cards
* Homework
* Homework text
* Homework image uploads
* Homework file uploads
* Protected Homework downloads
* Homework attachment expiry
* Fee Management
* Recurring monthly fees
* Student Fee Assignments
* Partial payments
* Payment reversals
* Student balances
* Student Financial Ledger
* Ledger totals
* School-branded receipts
* Parent Finance
* School Expenses
* Daily Cashbook / Daily Ledger
* Communication
* School announcements
* Parent notifications
* WhatsApp preferences
* n8n communication architecture
* Communication history
* Delivery status architecture
* Audit logs
* Demo school
* Demo parent account
* Health checks
* Deployment preparation
* Responsive desktop/tablet/mobile layouts

---

# Current Testing

The backend contains automated tests covering areas including:

* Authentication
* Tenant isolation
* School Administrator permissions
* Parent permissions
* Student access
* Class access
* Finance security
* Expenses
* Daily Cashbook
* Payment reversals
* Receipts
* Academics
* Homework
* Homework file validation
* Homework tenant isolation
* Parent Homework access
* Homework expiry
* File cleanup

Frontend validation uses:

```bash
npm run lint
npm run build
```

Backend validation uses:

```bash
python manage.py check
python manage.py test core.tests -v 2
python manage.py makemigrations --check --dry-run
```

Git whitespace validation can be run with:

```bash
git diff --check
```

---

# Remaining Deployment Work

The application is currently in deployment preparation.

Remaining work includes:

## Production Hosting

* Deploy Django
* Deploy React
* Configure PostgreSQL / Supabase
* Configure production environment variables
* Configure HTTPS
* Configure production domains
* Configure static files
* Configure media storage
* Configure backups
* Configure monitoring

## WhatsApp

Live WhatsApp still requires:

* Meta Business account
* WhatsApp Business Account
* WhatsApp phone number
* Meta Developer application
* Access credentials
* Approved WhatsApp templates
* Public n8n instance
* Webhook configuration
* Integration testing

## Scheduled Tasks

Production should schedule operations such as:

```text
Homework attachment cleanup
Recurring fee generation where required
Backup jobs
Other future scheduled processes
```

---

# Future Features

Potential future MTM functionality may include:

* Attendance
* Teacher Management
* Teacher accounts
* Teacher timetables
* Teacher class assignments
* More advanced financial reports
* Monthly income/expense reports
* Annual financial reports
* Expense category reporting
* CSV import
* Excel import
* Importing data from existing school systems
* Result withholding based on unpaid fees
* Per-school WhatsApp sender accounts
* Two-way WhatsApp messaging
* Progressive Web App support
* Native Android application
* Native iOS application

---

# Core Design Principles

MTM development follows these rules:

1. **Django is the authoritative application layer.**

2. **Each school is a separate tenant.**

3. **Tenant isolation is enforced on the backend.**

4. **The frontend never decides which school owns a record.**

5. **Parents only access linked children.**

6. **Students do not have login accounts.**

7. **Historical academic information is preserved.**

8. **Historical financial information is preserved.**

9. **Financial errors are corrected through reversals rather than silently deleting history.**

10. **Student billing and school operating expenses are separate financial concepts.**

11. **Student Financial Ledgers track the financial history of individual students.**

12. **The Daily Cashbook / Daily Ledger tracks actual school income and operational expenses.**

13. **Daily income is based on money actually received, not fees merely charged.**

14. **Daily Net Cash Movement equals valid payments received minus school expenses.**

15. **Every class uses one shared class timetable rather than creating duplicate timetables for every student.**

16. **Homework attachments are protected.**

17. **Homework attachment retention is limited.**

18. **n8n handles communication automation and delivery, not authoritative school business logic.**

19. **Passwords and secrets must never be committed to Git.**

20. **The web application should remain usable on desktop, tablet, and mobile devices.**

21. **PostgreSQL RLS may later provide additional defence in depth but does not replace Django permissions.**

---

# System Architecture

```text
                         MTM PLATFORM
                              │
              ┌───────────────┴───────────────┐
              │                               │
      PLATFORM ADMIN                  SCHOOL TENANTS
              │                               │
              │                    ┌──────────┼──────────┐
              │                    │          │          │
           Platform             School A   School B   School C
          Management               │          │          │
                                   │          │          │
                              Private     Private     Private
                              Records     Records     Records
                                   │
                      ┌────────────┴────────────┐
                      │                         │
                SCHOOL ADMIN              PARENT PORTAL
                      │                         │
                Own School                Own Children
                      │                         │
          ┌───────────┼────────────┐            │
          │           │            │            │
       Students    Academics    Finance       Homework
          │           │            │            │
       Parents     Results       Fees         Results
       Classes     Timetable     Payments     Finance
                   Homework      Receipts     Timetable
                                 Ledger       Receipts
                                 Expenses
                                 Cashbook
                      │
                  DJANGO API
                      │
                  PostgreSQL
                      │
              Supabase Hosting
               where configured
```

---

# Summary

The MTM School Management System is a multi-school platform combining:

* Student administration
* Parent management
* Academic management
* Class timetables
* Homework
* Results
* Report cards
* Student billing
* Payments
* Receipts
* Student Financial Ledgers
* School operating expenses
* Daily Cashbook / Daily Ledger
* Parent communication
* WhatsApp automation architecture
* Audit history
* Multi-school security

within one tenant-safe web application.

The system separates **student financial obligations** from **school operating expenses**.

The Student Financial Ledger explains the financial position of an individual student.

The Daily Cashbook / Daily Ledger records the school's actual daily incoming payments, outgoing expenses, and net cash movement.

Django remains the source of truth for permissions and business rules.

PostgreSQL provides the relational data layer.

React provides the responsive user interface.

n8n provides the external communication automation layer.

The application is currently in **deployment preparation** and is not yet considered fully production deployed.
