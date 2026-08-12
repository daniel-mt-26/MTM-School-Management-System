# MTM School Management System

## Overview

The MTM School Management System is a web based application designed to manage the daily administrative, academic, student and financial operations of multiple schools from one platform.

The system is designed as a **multi school platform**, where each school operates as a separate tenant with its own private data.

The system has three main user roles:

1. **MTM System Administrator**
2. **School Administrator/Receptionist**
3. **Parent/Guardian**

The MTM System Administrator manages the MTM platform itself but does not automatically have access to private school records.

Each School Administrator/Receptionist is associated with one school. When they log in, the system automatically determines which school they belong to. They do not need to enter a school ID when adding or managing records.

Parents have restricted access to information relating only to their own children.

---

# Multi School Structure

The same MTM system can be used by many schools.

For example:

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
```

Each school is isolated from the others.

A School A administrator cannot access School B's students, parents, fees, results or other private information.

The backend must enforce this separation rather than simply hiding information in the frontend.

---

# System Administrator

The MTM System Administrator manages the MTM platform rather than running the individual schools.

The System Administrator may manage:

* School accounts
* School registration
* Platform settings
* System status
* Subscription information
* Technical configuration

The System Administrator does not automatically have access to:

* Student personal information
* Parent information
* Student financial records
* Fee records
* Payment history
* Academic results
* Report cards
* Private school documents

Any future support access to private school data should be separately controlled and permission based.

---

# School Administrator / Receptionist

Each School Administrator is associated with one school.

For example:

```text
Administrator account
        ↓
School A
```

When the administrator logs in, the backend knows that the administrator belongs to School A.

When the administrator adds a student, they do not enter a school ID.

For example:

```text
Student name: John Smith
Parent: Mrs Smith
Class: Grade 2A
```

The system automatically uses the administrator's authorised school context.

The backend then verifies that the selected class belongs to the administrator's school.

---

# Class Structure

Each school can configure its own class structure.

Schools may have different numbers of classes for the same grade.

For example:

```text
School A

Grade 1A
Grade 1B
Grade 2A
Grade 2B
Grade 3A
```

Another school may have:

```text
School B

Grade 1A
Grade 2A
Grade 3A
```

Both schools can have a class called `Grade 2A`.

The class name does not need to be globally unique because the class belongs to a specific school.

Conceptually:

```text
School A
    └── Grade 2A
        └── Class ID 7

School B
    └── Grade 2A
        └── Class ID 15
```

The database uses the unique class ID to distinguish them.

The combination of school and class name should be unique within a school, preventing one school from accidentally creating two classes with the same name while allowing different schools to use the same class names.

---

# Student Management

Administrators can:

* Register students
* Edit student information
* View student profiles
* Search for students
* Assign students to classes
* Move students between classes
* Maintain student records

Students are associated with a class.

The class belongs to a school.

Conceptually:

```text
School
   ↓
Class
   ↓
Student
```

The student's school context can therefore be established through the administrator's school and the student's class.

The system must verify that a student is not assigned to a class belonging to another school.

---

# Parent Management

Parents will have secure accounts.

One parent account can be linked to multiple students.

For example:

```text
Mrs Smith
   │
   ├── John Smith
   ├── Sarah Smith
   └── Michael Smith
```

This allows one parent to manage the information for multiple children attending the same school.

Parents can:

* View their children's profiles
* View their children's classes
* View school fees
* View outstanding balances
* View payment history
* View financial ledgers
* Access receipts
* Receive notifications
* Update permitted contact information

Parents cannot modify financial or administrative records.

---

# Parent Portal

Parents will have their own secure portal.

The portal will only display information belonging to the children associated with their account.

For example:

```text
Parent: Mrs Smith

Children:

John Smith
Grade 3A

Sarah Smith
Grade 1B
```

The parent should not be able to access another family's information.

---

# Fee Management

Administrators can:

* Create and edit fee structures
* Set fees by class
* Set fees by school term
* Assign fees to students
* Record payments
* Accept partial payments
* Track outstanding balances

Parents can view the fees assigned to their children and their current balances.

---

# Payment Management

The system records payments made towards a student's account.

Example:

```text
Amount owed:       $300
Payment made:      $100
Remaining balance: $200
```

Partial payments are supported.

Every payment remains in the student's payment history.

---

# Student Financial Ledger

Each student has an individual financial ledger showing their fee and payment history.

Example:

| Date   | Description | Debit | Credit | Balance |
| ------ | ----------- | ----: | -----: | ------: |
| Jan 10 | Term fees   |  $300 |        |    $300 |
| Jan 15 | Payment     |       |   $100 |    $200 |
| Jan 30 | Payment     |       |    $50 |    $150 |

Administrators can manage the ledger.

Parents can view their child's financial history.

---

# Receipts

When a payment is recorded, the system can:

* Generate a receipt
* Assign a unique receipt number
* Store the receipt
* Link the receipt to the student's account
* Allow parents to access receipts through the parent portal
* Support sharing receipts through WhatsApp

---

# Class Management

Administrators can create and manage classes.

The system is not limited to a fixed class structure.

Example:

```text
Baby Class
ECD B
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

Each school can configure its own classes.

---

# School Term Management

The system manages:

* School terms
* Term dates
* Current term
* Previous terms
* Fees associated with each term
* Student payment history by term

Historical financial information is retained when a new term begins.

---

# Academic Results

The system will support student academic results.

Administrators will eventually be able to:

* Enter student results
* View student results
* Store results by subject
* Store results by term
* Store historical results
* Generate student report cards

Parents will be able to view their children's academic results through the parent portal.

### Future update

The system may later support withholding grades or results when school fees have not been paid, according to the school's policy.

This will be implemented as a later feature and is not part of the initial core system.

---

# Administrator Dashboard

The administrator dashboard provides an overview of their school.

It can display:

* Total students
* Active parent accounts
* Current school term
* Fees collected
* Outstanding fees
* Recent payments
* Students with outstanding balances
* Recent student registrations
* Academic information

The administrator only sees information belonging to their school.

---

# Parent Dashboard

The parent dashboard provides information relevant to the parent's children.

Example:

```text
Child: John Smith
Class: Grade 3A

Current fees:       $400
Paid:               $250
Outstanding:        $150
```

Parents can access:

* Student information
* Fee information
* Payment history
* Financial ledger
* Receipts
* Academic results
* Report cards
* Notifications

---

# Authentication and Permissions

The system uses role based access.

| Function                  | MTM System Admin                 | School Admin              | Parent            |
| ------------------------- | -------------------------------- | ------------------------- | ----------------- |
| Platform management       | Full access                      | No access                 | No access         |
| School account management | Full access                      | Own school only           | No access         |
| Student management        | No automatic private access      | Full access to own school | Own children only |
| Fee management            | No automatic private access      | Full access to own school | View              |
| Payment management        | No automatic private access      | Create and manage         | View              |
| Financial ledger          | No automatic private access      | Full access to own school | Own children only |
| Receipts                  | No automatic private access      | Create and manage         | Own children only |
| Class management          | Platform level where appropriate | Own school only           | View              |
| Academic results          | No automatic private access      | Manage own school         | Own children only |
| Reports                   | Platform reports                 | Own school reports        | No access         |
| User management           | Platform level                   | Own school users          | Own account       |

Parents must only be able to access information belonging to their own children.

School administrators must only be able to access information belonging to their own school.

---

# Notifications

The system can notify parents about:

* New fees
* Payments received
* Outstanding balances
* Receipts
* Academic results
* Important school announcements

Notifications may be delivered through:

* Parent portal
* Email
* WhatsApp

---

# Reports

Administrators can generate reports including:

* Fee collection reports
* Outstanding fee reports
* Payment reports
* Student lists
* Class lists
* Term reports
* Individual student statements
* Academic reports
* Report cards

School administrators only have access to reports belonging to their own school.

---

# Database Structure

The database is designed around the school as the primary organisation.

Conceptually:

```text
MTM PLATFORM
│
├── School A
│   │
│   ├── School Users
│   ├── Parents
│   ├── Classes
│   │     │
│   │     └── Students
│   ├── Subjects
│   ├── Academic Years
│   ├── Terms
│   ├── Fees
│   ├── Payments
│   ├── Financial Ledgers
│   ├── Academic Results
│   ├── Report Cards
│   ├── Receipts
│   └── Notifications
│
├── School B
│   │
│   └── Its own private records
│
└── School C
    │
    └── Its own private records
```

A student is assigned to a class.

Each class belongs to a school.

The administrator's authenticated school is used by the backend when creating and managing records.

The backend verifies that related records belong to the same school.

---

# System Architecture

```text
                         MTM PLATFORM
                              |
             +----------------+----------------+
             |                                 |
      MTM SYSTEM ADMIN                  SCHOOL TENANTS
             |                                 |
      Platform management          +-----------+-----------+
      School accounts              |           |           |
      System status             School A    School B    School C
      Subscription status          |           |           |
                                   |           |           |
                                Private     Private     Private
                                school      school      school
                                records     records     records
                                   |
                         +---------+---------+
                         |                   |
                  SCHOOL ADMIN          PARENT PORTAL
                         |                   |
                  Own school only      Own children only
                         |
                  Student Management
                  Class Management
                  Fee Management
                  Payments
                  Financial Ledgers
                  Academic Results
                  Report Cards
                  Reports
                  User Management
                         |
                      BACKEND
                      Django
                         |
                        API
                         |
                      DATABASE
                     PostgreSQL
```

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

## Database

* PostgreSQL

## Development Tools

* Visual Studio Code
* Git
* GitHub

---

# Development Approach

The system will be developed incrementally.

Initial development stages:

1. Project setup
2. React frontend
3. Django backend
4. PostgreSQL database
5. Database fundamentals and relationships
6. Multi school architecture
7. Authentication and permissions
8. School management
9. Class management
10. Student management
11. Parent management
12. Student profiles
13. Fee management
14. Payment management
15. Financial ledger
16. Academic results
17. Receipts
18. Administrator dashboard
19. Parent portal
20. Report cards
21. Reports
22. Notifications
23. WhatsApp integration
24. Testing
25. Deployment

The system will be developed with school data isolation and role based permissions as core architectural requirements rather than features added later.
