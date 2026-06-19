# NN Fund Management Module

> **Odoo 18 Technical Assessment — NN Services & Engineering Ltd.**  
> A comprehensive fund management system with multi-level approval workflows, real-time balance tracking, and complete audit trails.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Assumptions & Known Limitations](#assumptions--known-limitations)
5. [Prerequisites](#prerequisites)
6. [Quick Start (Docker)](#quick-start-docker)
7. [Manual Installation](#manual-installation)
8. [Module Configuration](#module-configuration)
9. [Demo Walkthrough](#demo-walkthrough)
10. [Security Model](#security-model)
11. [Technical Details](#technical-details)
12. [Testing](#testing)
13. [Project Structure](#project-structure)

---

## Overview

The **NN Fund Management** module (`nn_fund_management`) provides end-to-end fund lifecycle management for organizations. It tracks money from the moment it enters a fund account, through allocation to projects and expense heads, requisition for spending, and ultimately vendor bill payment — all governed by a multi-level approval workflow (GM → MD).

### Key Capabilities

- **Fund Account Management** — Track multiple bank/cash accounts with real-time balance summaries
- **Incoming Fund Recording** — Record and confirm money received, with duplicate detection
- **Fund Allocation** — Allocate funds from accounts to projects or expense heads with approval
- **Fund Requisition** — Request spending from projects/expense heads with bill tracking
- **Bill Control** — Integrated with Odoo's native Vendor Bills; enforces spending limits
- **Fund Transfer** — Transfer funds between projects and expense heads
- **Multi-Level Approval** — Draft → Submitted → GM Approval → MD Approval → Approved
- **Complete Audit Trail** — Every action recorded with who, when, what, and why
- **Dashboard** — Quick overview of fund status and pending approvals

---

## Features

### Core Features (Assessment Requirements)

| # | Feature | Status |
|---|---------|--------|
| 1 | Fund Account CRUD | ✅ |
| 2 | Incoming Fund (record, confirm, cancel) | ✅ |
| 3 | Project & Expense Head Master Data | ✅ |
| 4 | Fund Allocation with Approval | ✅ |
| 5 | Fund Requisition with Bill Tracking | ✅ |
| 6 | Bill Control (Odoo Vendor Bill integration) | ✅ |
| 7 | Fund Transfer between Projects/Expense Heads | ✅ |
| 8 | Multi-Level Approval Workflow (GM → MD) | ✅ |
| 9 | Real-time Balance Computation | ✅ |
| 10 | Complete Audit History | ✅ |
| 11 | Role-based Security & Access Control | ✅ |
| 12 | Automated Test Suite | ✅ |

### Bonus Features

| # | Feature | Status |
|---|---------|--------|
| 1 | Dashboard with Quick Actions | ✅ |
| 2 | Demo Data (matches assessment scenarios) | ✅ |
| 3 | Dockerized Deployment | ✅ |
| 4 | Concurrency-safe Balance Validation (FOR UPDATE) | ✅ |
| 5 | Self-approval Prevention | ✅ |

---

## Architecture

### Data Model

```
Fund Account (nn.fund.account)
├── Incoming Funds (nn.fund.incoming)
│   └── Draft → Confirmed → [Cancelled]
└── Allocations (nn.fund.allocation)
    └── Draft → Submitted → GM → MD → Approved → [Rejected/Cancelled]

Project (nn.fund.project)          Expense Head (nn.fund.expense.head)
├── Requisitions (nn.fund.requisition)
│   ├── Draft → Submitted → GM → MD → Approved → [Closed]
│   └── Bills (account.move, move_type='in_invoice')
└── Transfers (nn.fund.transfer)
    └── Draft → Submitted → GM → MD → Approved → [Rejected/Cancelled]
```

### Balance Computation (All `store=True`, `readonly=True`)

**Fund Account:**
```
unassigned_balance = total_received - total_assigned - amount_on_hold
```

**Project / Expense Head:**
```
available_balance = total_allocated + incoming_transfers - outgoing_transfers
                  - requisition_hold - transfer_hold - approved_unspent - total_spent
```

### Approval Workflow (Reusable Mixin)

```
┌─────────┐    ┌───────────┐    ┌─────────────┐    ┌──────────┐
│  Draft  │───→│ Submitted │───→│ GM Approved │───→│ Approved │
└─────────┘    └───────────┘    └─────────────┘    └──────────┘
                    │                  │
                    │ GM Reject        │ MD Reject
                    ↓                  ↓
               ┌──────────┐      ┌──────────┐
               │ Rejected │      │ Rejected │
               └──────────┘      └──────────┘
```

### Concurrency Safety

All balance-checking operations use PostgreSQL `SELECT ... FOR UPDATE` row-level locks to prevent double-spending in concurrent scenarios:

```python
def _on_submit_validate(self):
    self._lock_balance_record(self.fund_account_id)  # Blocks concurrent requests
    self.fund_account_id.invalidate_recordset(['unassigned_balance'])
    available = self.fund_account_id.unassigned_balance
    if self.amount > available:
        raise UserError(...)
```

---

## Assumptions & Known Limitations

### Assumptions
1. **Multi-Company Operations**: It is assumed that fund accounts, projects, and expense heads belong to specific companies, and cross-company fund allocations are not permitted by default.
2. **Approval Hierarchy**: The requirement states GM and MD approval. It is assumed that *any* user in the GM group can approve Level 1, and *any* user in the MD group can approve Level 2, rather than routing to a specific employee's direct manager.
3. **Bill Lifecycle**: It is assumed that Vendor Bills (account.move) generated against a Requisition are managed by the Accounting department. The Requisition's `total_billed` relies strictly on the `posted` state of the invoice.

### Known Limitations
1. **Bank Email Integration**: The Bank Email Integration is currently a conceptual prototype/bonus feature and does not have active IMAP fetching capabilities in this build to avoid storing hardcoded credentials.
2. **Dynamic Approval Routing**: Approval rules are strictly tied to Odoo Security Groups. Highly dynamic rule engines (e.g., routing based on specific departmental thresholds) would require an extension of the `nn.approval.mixin`.
3. **Multi-Currency**: While currency fields are implemented using `res.currency`, extreme multi-currency scenarios (where the Bank Account, Project, and Vendor Bill are all in entirely different currencies) rely on Odoo's base currency conversion rates at the time of posting, which may result in slight rounding discrepancies in `remaining_billable` fields.

---

## Prerequisites

- **Docker** & **Docker Compose** (recommended)
- OR: **Python 3.10+**, **PostgreSQL 14+**, **Odoo 18.0**

---

## Quick Start (Docker)

```bash
# 1. Clone the repository
git clone <repository-url>
cd NNSEL

# 2. Copy environment file
cp .env.example .env

# 3. Build and start
docker compose up -d --build

# 4. Access Odoo
# Open http://localhost:8069

# 5. Create database
# Database Name: nn_fund
# Email: admin
# Password: admin
# ✅ Check "Load demonstration data" for demo data

# 6. Install the module
# Go to Apps → Search "Fund Management" → Install
```

### Docker Services

| Service | Container | Port |
|---------|-----------|------|
| Odoo 18 | `nn-odoo18` | 8069 |
| PostgreSQL 16 | `nn-odoo-db` | (internal) |

---

## Manual Installation

1. Install Odoo 18.0 following the [official guide](https://www.odoo.com/documentation/18.0/administration/install.html)
2. Copy the `addons/nn_fund_management` folder into your Odoo addons path
3. Update the addons list: `Settings → Apps → Update Apps List`
4. Search for "NN Fund Management" and install

---

## Module Configuration

### 1. Assign User Roles

After installation, assign users to the appropriate security groups:

| Group | Who Should Have It |
|-------|-------------------|
| Fund User | All employees who view fund data |
| Finance User | Finance team members who confirm incoming funds |
| GM Approver | General Managers who approve at Level 1 |
| MD Approver | Managing Directors who approve at Level 2 |
| Fund Administrator | IT/Finance admins with full access |

Go to: `Settings → Users & Companies → Users → Select User → Other tab`

### 2. Demo Users (if demo data loaded)

| User | Login | Password | Role |
|------|-------|----------|------|
| Fund User (Demo) | `demo_fund_user` | `demo_fund_user` | Fund User |
| Finance Officer (Demo) | `demo_finance` | `demo_finance` | Finance User |
| General Manager (Demo) | `demo_gm` | `demo_gm` | GM Approver |
| Managing Director (Demo) | `demo_md` | `demo_md` | MD Approver |
| Fund Administrator (Demo) | `demo_admin` | `demo_admin` | Administrator |

---

## Demo Walkthrough

This walkthrough matches the **Sample Demonstration Steps** from the technical assessment.

### Step 1: Record Incoming Funds

1. Navigate to **Fund Management → Operations → Fund Accounts**
2. Create account "Main Bank Account" (type: Bank)
3. Go to **Operations → Incoming Funds → Create**
4. Select fund account, enter amount (e.g., 5,000,000), add transaction reference
5. Click **Confirm** (requires Finance User role)
6. Verify the fund account's "Unassigned Balance" is updated

### Step 2: Create Projects & Expense Heads

1. Go to **Master Data → Projects** → Create "Project Alpha", "Project Beta"
2. Go to **Master Data → Expense Heads** → Create "Office Rent", "Staff Salary"

### Step 3: Allocate Funds

1. Go to **Operations → Allocations → Create**
2. Select fund account → Allocate to Project Alpha → Amount: 2,000,000
3. Click **Submit** → System validates unassigned balance
4. Login as GM → Click **GM Approve**
5. Login as MD → Click **MD Approve**
6. Verify: Fund account unassigned balance decreased, Project Alpha balance increased

### Step 4: Create Requisition

1. Go to **Operations → Requisitions → Create**
2. Select Project Alpha → Amount: 500,000 → Purpose: "Equipment purchase"
3. Submit → GM Approve → MD Approve
4. Verify: Project Alpha's "Available Balance" decreased

### Step 5: Create & Link Vendor Bill

1. Go to **Accounting → Vendors → Bills → Create**
2. Add vendor, bill lines totaling 300,000
3. In the **Fund Requisition** field, select the approved requisition
4. Post the bill → System validates amount ≤ remaining billable

### Step 6: Test Bill Over-Spending Block

1. Create another bill for 250,000 against the same requisition
2. Try to post → **System blocks it** (only 200,000 remaining)

### Step 7: Fund Transfer

1. Go to **Operations → Transfers → Create**
2. Source: Project Alpha → Destination: Project Beta → Amount: 500,000
3. Submit → GM Approve → MD Approve
4. Verify: Project Alpha decreased, Project Beta increased

### Step 8: Review Audit Trail

1. Go to **Reporting → Approval History**
2. View all actions with timestamps, users, and amounts

---

## Security Model

### Hierarchical Groups

```
Fund User (Base)
└── Finance User (+ incoming fund management)
    └── GM Approver (+ Level 1 approval)
        └── MD Approver (+ Level 2 approval)
            └── Fund Administrator (full access)
```

### Access Control Matrix

| Model | Fund User | Finance | GM | MD | Admin |
|-------|-----------|---------|----|----|-------|
| Fund Account | R | RWCU | RWCU | RWCU | RWCUD |
| Incoming Fund | R | RWC | RWC | RWC | RWCUD |
| Project | R | RWC | RWC | RWC | RWCUD |
| Expense Head | R | RWC | RWC | RWC | RWCUD |
| Allocation | RWC | RWC | RWC | RWC | RWCUD |
| Requisition | RWC | RWC | RWC | RWC | RWCUD |
| Transfer | RWC | RWC | RWC | RWC | RWCUD |
| Approval History | R | R | R | R | RWCUD |

*R=Read, W=Write, C=Create, U=Update, D=Delete*

### Server-Side Constraints

All security constraints are enforced server-side (not just UI hiding):

- ✅ State-based field readonly enforcement
- ✅ Group-based action method checks (`has_group()`)
- ✅ Self-approval prevention (requester ≠ approver)
- ✅ Non-draft deletion blocking
- ✅ Balance validation with FOR UPDATE locks
- ✅ Bill over-spending prevention in `_post()` override

---

## Technical Details

### Dependencies

| Module | Purpose |
|--------|---------|
| `base` | Core Odoo functionality |
| `mail` | Chatter, tracking, activities |
| `account` | Vendor bill integration (account.move) |

### Key Design Decisions

1. **Reusable Approval Mixin** (`nn.approval.mixin`): AbstractModel with hook methods for each lifecycle event, reducing code duplication across allocation, requisition, and transfer models.

2. **Native Vendor Bill Integration**: Instead of a custom bill model, we inherit `account.move` and override `_post()` to inject fund constraints. This leverages Odoo's full accounting stack.

3. **Stored Computed Fields**: All balance fields use `store=True`, `readonly=True`. This enables:
   - Database-level filtering and sorting
   - Efficient list view rendering
   - Tree view aggregation (sum totals)

4. **FOR UPDATE Concurrency Locks**: The `_lock_balance_record()` method acquires PostgreSQL row-level locks before balance validation, preventing race conditions in multi-user environments.

5. **Standalone Project Model**: Uses `nn.fund.project` instead of inheriting `project.project` to avoid unnecessary dependencies and keep the module lightweight.

---

## Testing

### Run Tests

```bash
# Inside Docker
docker exec -it nn-odoo18 odoo -d nn_fund --test-enable --stop-after-init \
  -i nn_fund_management --log-level=test

# Manual installation
python odoo-bin -d nn_fund --test-enable --stop-after-init \
  -i nn_fund_management --log-level=test
```

### Test Coverage

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_fund_account.py` | 8 | Account CRUD, incoming confirm/cancel, duplicate ref, permissions |
| `test_fund_allocation.py` | 10 | Full workflow, rejection, over-allocation, GM/MD ordering |
| `test_fund_requisition.py` | 5 | Workflow, hold mechanics, over-requisition, close action |
| `test_fund_bill.py` | 5 | Partial billing, over-billing block, cancel restore, unapproved block |
| `test_fund_transfer.py` | 5 | P2P transfer, same src/dest block, over-transfer, rejection release |
| **Total** | **33** | All critical paths |

---

## Project Structure

```
NNSEL/
├── docker-compose.yml          # Docker Compose for Odoo 18 + PostgreSQL 16
├── Dockerfile                  # Extends odoo:18.0 with custom addons
├── odoo.conf                   # Odoo server configuration
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── README.md                   # This file
│
└── addons/
    └── nn_fund_management/
        ├── __manifest__.py     # Module metadata and dependencies
        ├── __init__.py         # Package init
        │
        ├── models/
        │   ├── approval_mixin.py       # Reusable approval workflow (AbstractModel)
        │   ├── approval_history.py     # Audit trail model
        │   ├── fund_account.py         # Fund account with computed balances
        │   ├── fund_incoming.py        # Incoming fund (draft → confirmed)
        │   ├── fund_project.py         # Project with 8 balance fields
        │   ├── fund_expense_head.py    # Expense head (mirrors project)
        │   ├── fund_allocation.py      # Fund allocation with approval
        │   ├── fund_requisition.py     # Fund requisition with bill tracking
        │   ├── fund_transfer.py        # Inter-project/expense transfers
        │   └── account_move.py         # Vendor bill inheritance
        │
        ├── views/
        │   ├── menu_views.xml              # Menu structure
        │   ├── dashboard_views.xml         # Dashboard with quick actions
        │   ├── fund_account_views.xml      # Fund account tree/form/search
        │   ├── fund_incoming_views.xml     # Incoming fund views
        │   ├── fund_allocation_views.xml   # Allocation views with workflow
        │   ├── fund_project_views.xml      # Project views with balance tabs
        │   ├── fund_expense_head_views.xml # Expense head views
        │   ├── fund_requisition_views.xml  # Requisition views with bills
        │   ├── fund_transfer_views.xml     # Transfer views
        │   ├── account_move_views.xml      # Vendor bill form extension
        │   └── approval_history_views.xml  # Audit trail views
        │
        ├── security/
        │   ├── security_groups.xml     # 5 hierarchical security groups
        │   ├── ir.model.access.csv     # Access control matrix
        │   └── ir_rules.xml           # Multi-company record rules
        │
        ├── data/
        │   ├── sequence_data.xml       # Auto-number sequences
        │   └── demo_data.xml           # Demo users, accounts, projects
        │
        ├── static/
        │   └── description/
        │       └── icon.svg            # Module icon
        │
        └── tests/
            ├── test_fund_account.py        # 8 tests
            ├── test_fund_allocation.py     # 10 tests
            ├── test_fund_requisition.py    # 5 tests
            ├── test_fund_bill.py           # 5 tests
            └── test_fund_transfer.py       # 5 tests
```

---

## License

LGPL-3 (standard Odoo module license)

## Author

Developed for the Trainee Software Developer technical assessment at NN Services & Engineering Ltd.
