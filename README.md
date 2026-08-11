# MTM School Management System

## Overview

The MTM School Management System is a web based application designed to manage the administrative, academic, student and financial operations of a school.

The system is designed as a **multi school platform**, meaning the same software can be used by multiple schools. Each school has its own students, parents, classes, fees, payments, academic records and settings.

The system has two main user types:

1. **School Administrator/Receptionist**
2. **Parent/Guardian**

The administrator has full control over the school's records, while parents have restricted access to information relating to their own children.

## Multi School Platform

MTM SMS is designed so that multiple schools can use the same platform without sharing their data.

Each school can configure its own:

* School information
* Classes
* Academic years
* Terms
* Subjects
* Fee structures
* Grading system
* Students
* Parents
* Teachers and authorised users
* Academic records

One school may have one class per grade, while another may have multiple classes.

For example:

```text
School A

Grade 1
    Grade 1A
    Grade 1B

Grade 2
    Grade 2A
    Grade 2B
```

Another school may have:

```text
School B

Grade 1
Grade 2
Grade 3
```

The system will allow each school to configure its own class structure rather than using a fixed structure.

## Main Features

### 1. Student Management

Administrators can:

* Register students
* Edit student information
* View student profiles
* Search for students
* Assign students to classes
* Move students between classes
* Maintain student records
* Maintain student history

Parents can:

* View their child's profile
* View their child's class
* View relevant information about their child

### 2. Parent Portal

Parents will have their own secure accounts.

Through the parent portal, parents can:

* View their child's information
* View their child's class
* View current school fees
* View outstanding balances
* View payment history
* View their child's financial ledger
* View academic results
* View academic history
* View and access payment receipts
* Receive school notifications
* Update permitted contact information

Parents cannot modify financial records, academic results or administrative information.

### 3. Fee Management

Administrators can:

* Create and edit fee structures
* Set fees by class
* Set fees by term
* Assign fees to students
* Record payments
* Accept partial payments
* Track outstanding balances
* Manage different fees for different classes where required

Parents can:

* View fees assigned to their children
* View amounts paid
* View outstanding balances
* View their child's fee history

### 4. Payment Management

The system records all payments made towards a student's account.

For example:

```text
Amount owed:       $300
Payment made:      $100
Remaining balance: $200
```

Partial payments are supported, and every payment is retained in the student's payment history.

The system should maintain a complete record of each transaction rather than simply replacing the previous balance.

### 5. Student Financial Ledger

Each student has an individual financial ledger showing their complete fee and payment history.

Example:

| Date   | Description | Debit | Credit | Balance |
| ------ | ----------- | ----: | -----: | ------: |
| Jan 10 | Term fees   |  $300 |        |    $300 |
| Jan 15 | Payment     |       |   $100 |    $200 |
| Jan 30 | Payment     |       |    $50 |    $150 |

Administrators can manage the ledger, while parents can view their child's financial history.

### 6. Academic Results Management

The system will allow schools to record and manage student academic results.

Administrators or authorised academic staff can record:

* Subject
* Assessment
* Mark obtained
* Total mark
* Percentage
* Term
* Academic year
* Class
* Teacher comments
* Grade where applicable

Example:

```text
Student: John Smith
Class: Grade 3A
Term: Term 2
Academic Year: 2026

Subject       Mark       Percentage
Mathematics   72/100       72%
English       81/100       81%
Science       68/100       68%
```

The system will maintain historical academic records so that results from previous terms and academic years can be accessed.

Schools should also be able to configure their grading system rather than being forced to use one fixed grading structure.

Parents can view their child's academic results through the parent portal.

### 7. Report Cards

The system can eventually generate student report cards containing:

* Student information
* Class
* Academic year
* Term
* Subjects
* Results
* Grades
* Teacher comments
* Overall performance

Parents can access their child's report cards through the parent portal.

### 8. Receipts

When a payment is recorded, the system can:

* Generate a receipt
* Assign a unique receipt number
* Store the receipt
* Link the receipt to the student's account
* Allow parents to access receipts through the parent portal
* Support sharing receipts through WhatsApp

### 9. Class Management

Administrators can create and manage classes according to their school's structure.

The system does not assume that every school has the same number of classes per grade.

For example:

```text
Grade 1
    Grade 1A
    Grade 1B

Grade 2
    Grade 2A

Grade 3
    Grade 3A
    Grade 3B
    Grade 3C
```

Each class can contain its own students and can optionally have additional information such as:

* Class name
* Grade
* Teacher
* Capacity
* Academic year

### 10. School Term and Academic Year Management

The system manages:

* Academic years
* School terms
* Term dates
* Current term
* Previous terms
* Fees associated with each term
* Student payment history by term
* Academic results by term

Historical financial and academic information is retained when a new term or academic year begins.

### 11. Administrator Dashboard

The administrator dashboard provides an overview of the school.

It can display:

* Total students
* Active parent accounts
* Current academic year
* Current school term
* Fees collected
* Outstanding fees
* Recent payments
* Students with outstanding balances
* Recent student registrations
* Academic information
* Important notifications

### 12. Parent Dashboard

The parent dashboard provides information relevant to the parent's children.

Example:

```text
Welcome, Parent

Child: John Smith
Class: Grade 3A

Current fees:       $400
Paid:               $250
Outstanding:        $150

Latest result:
Mathematics         72%

Recent payment:
$100
```

Parents can access:

* Student information
* Class information
* Fee information
* Payment history
* Financial ledger
* Receipts
* Academic results
* Report cards
* Notifications

### 13. Authentication and Permissions

The system uses role based access.

| Function           | Administrator | Parent         |
| ------------------ | ------------- | -------------- |
| Student management | Full access   | Own child only |
| Fee management     | Full access   | View           |
| Payment management | Create/Edit   | View           |
| Financial ledger   | Full access   | View           |
| Receipts           | Create/Manage | View           |
| Class management   | Full access   | View           |
| Academic results   | Create/Edit   | View           |
| Report cards       | Create/Manage | View           |
| Reports            | Full access   | No access      |
| User management    | Full access   | Own account    |

Parents must only be able to access information belonging to their own children.

### 14. Notifications

The system can notify parents about:

* New fees
* Payments received
* Outstanding balances
* Receipts
* Academic results
* Report cards
* Important school announcements

Notifications may eventually be delivered through:

* Parent portal
* Email
* WhatsApp

### 15. Reports

Administrators can generate reports including:

* Fee collection reports
* Outstanding fee reports
* Payment reports
* Student lists
* Class lists
* Academic results
* Academic performance reports
* Term reports
* Individual student statements
* Student report cards

Parents do not have access to the school's overall financial or administrative reports.

## Data Structure

The system will be designed around the school as the primary organisation.

Conceptually:

```text
School
    |
    +-- Users
    |
    +-- Parents
    |
    +-- Students
    |
    +-- Classes
    |
    +-- Subjects
    |
    +-- Academic Years
    |
    +-- Terms
    |
    +-- Fees
    |
    +-- Payments
    |
    +-- Financial Ledgers
    |
    +-- Academic Results
    |
    +-- Report Cards
    |
    +-- Receipts
    |
    +-- Notifications
```

Each school's records must remain isolated from other schools using the platform.

## System Architecture

```text
                    MTM SCHOOL MANAGEMENT SYSTEM
                                |
                +---------------+---------------+
                |                               |
          ADMIN PORTAL                    PARENT PORTAL
                |                               |
        Student Management               Child Information
        Class Management                 Fees
        Fee Management                   Payments
        Payments                         Ledger
        Financial Ledgers                Receipts
        Receipts                         Results
        Academic Results                 Report Cards
        Report Cards                     Notifications
        Reports
        User Management
                |                               |
                +---------------+---------------+
                                |
                            BACKEND
                            Django
                                |
                              API
                                |
                            DATABASE
                           PostgreSQL
                                |
                +---------------+---------------+
                |               |               |
             School A        School B        School C
             Data            Data            Data
```

## Technology Stack

### Frontend

* React
* Vite
* JavaScript
* HTML
* CSS

### Backend

* Python
* Django
* Django REST Framework

### Database

* PostgreSQL

### Development Tools

* Visual Studio Code
* Git
* GitHub

## Development Approach

The system will be developed incrementally.

### Initial Development

1. Project setup
2. React frontend
3. Django backend
4. PostgreSQL database
5. Multi school database structure
6. Student management
7. Class management
8. Student profiles
9. Parent accounts
10. Fee management
11. Payment management
12. Financial ledger
13. Academic results

### Additional Development

14. Receipts
15. Administrator dashboard
16. Parent portal
17. Authentication and permissions
18. Report cards
19. Reports
20. Notifications
21. WhatsApp integration
22. Testing
23. Deployment

### Future Updates

Data migration and importing will be developed as a future feature.

The initial version will target schools that do not currently have a school management system. These schools will enter their initial student, parent, class and fee information directly into MTM SMS.

Future versions may support:

* CSV imports
* Excel imports
* Data mapping
* Duplicate detection
* Historical data migration
* API integrations with existing school management systemsgit status

## Product Goal

MTM SMS is intended to become a reusable school management platform rather than a system built for one individual school.

The same application should be capable of serving schools with different:

* Class structures
* Number of classes per grade
* Fee structures
* Academic terms
* Subjects
* Grading systems
* Student populations
* School configurations

Each school should be able to configure the system to match its own requirements while using the same underlying MTM SMS platform.
