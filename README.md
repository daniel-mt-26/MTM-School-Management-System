# MTM School Management System

## Overview

The MTM School Management System is a web based application designed to manage the daily administrative, student and financial operations of a school.

The system has two main user types:

1. **School Administrator/Receptionist**
2. **Parent/Guardian**

The administrator has full control over the school's records, while parents have restricted access to information relating to their own children.

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

Parents can:

* View their child's profile
* View their child's class
* View relevant information about their child

### 2. Parent Portal

Parents will have their own secure accounts.

Through the parent portal, parents can:

* View their child's information
* View current school fees
* View outstanding balances
* View payment history
* View their child's financial ledger
* View and access payment receipts
* Receive school notifications
* Update permitted contact information

Parents cannot modify financial records or administrative information.

### 3. Fee Management

Administrators can:

* Create and edit fee structures
* Set fees by class
* Set fees by school term
* Assign fees to students
* Record payments
* Accept partial payments
* Track outstanding balances

Parents can view the fees assigned to their children and their current balances.

### 4. Payment Management

The system records all payments made towards a student's account.

For example:

```text
Amount owed:       $300
Payment made:      $100
Remaining balance: $200
```

Partial payments are supported, and every payment is retained in the student's payment history.

### 5. Student Financial Ledger

Each student has an individual financial ledger showing their complete fee and payment history.

Example:

| Date   | Description | Debit | Credit | Balance |
| ------ | ----------- | ----- | ------ | ------- |
| Jan 10 | Term fees   | $300  |        | $300    |
| Jan 15 | Payment     |       | $100   | $200    |
| Jan 30 | Payment     |       | $50    | $150    |

Administrators can manage the ledger, while parents can view their child's financial history.

### 6. Receipts

When a payment is recorded, the system can:

* Generate a receipt
* Assign a unique receipt number
* Store the receipt
* Link the receipt to the student's account
* Allow parents to access their receipts through the parent portal
* Support sharing receipts through WhatsApp

### 7. Class Management

Administrators can create and manage school classes.

The system is designed to support classes such as:

```text
Baby Class
ECD B
Grade 1
Grade 2
Grade 3
Grade 4
Grade 5
Grade 6
Grade 7
```

Students can be assigned to their respective classes, and parents can view their child's current class.

### 8. School Term Management

The system manages:

* School terms
* Term dates
* Current term
* Previous terms
* Fees associated with each term
* Student payment history by term

Historical financial information is retained when a new term begins.

### 9. Administrator Dashboard

The administrator dashboard provides an overview of the school.

It can display:

* Total students
* Active parent accounts
* Current school term
* Fees collected
* Outstanding fees
* Recent payments
* Students with outstanding balances
* Recent student registrations

### 10. Parent Dashboard

The parent dashboard provides information relevant to the parent's children.

It can display:

```text
Child: John Smith
Class: Grade 3

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
* Notifications

### 11. Authentication and Permissions

The system uses role based access.

| Function           | Administrator | Parent         |
| ------------------ | ------------- | -------------- |
| Student management | Full access   | Own child only |
| Fee management     | Full access   | View           |
| Payment management | Create/Edit   | View           |
| Financial ledger   | Full access   | View           |
| Receipts           | Create/Manage | View           |
| Class management   | Full access   | View           |
| Reports            | Full access   | No access      |
| User management    | Full access   | Own account    |

Parents must only be able to access information belonging to their own children.

### 12. Notifications

The system can notify parents about:

* New fees
* Payments received
* Outstanding balances
* Receipts
* Important school announcements

Notifications may be delivered through the parent portal, email or WhatsApp.

### 13. Reports

Administrators can generate reports including:

* Fee collection reports
* Outstanding fee reports
* Payment reports
* Student lists
* Class lists
* Term reports
* Individual student statements

Parents do not have access to the school's overall financial reports.

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
        Receipts                         Notifications
        Reports
        User Management
                |                               |
                +---------------+---------------+
                                |
                            BACKEND
                            Django
                                |
                            DATABASE
                           PostgreSQL
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

The initial development stages will focus on:

1. Project setup
2. React frontend
3. Django backend
4. PostgreSQL database
5. Student management
6. Class management
7. Student profiles
8. Fee management
9. Payment management
10. Financial ledger

The parent portal, notifications, reporting and additional features will be developed after the core school management functionality is operational.
