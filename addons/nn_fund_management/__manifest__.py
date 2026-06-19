# -*- coding: utf-8 -*-
{
    'name': 'NN Fund Management',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Fund Management',
    'summary': 'Manage incoming funds, allocations, requisitions, bills and transfers '
               'with multi-level approval workflows.',
    'description': """
NN Fund Management Module
=========================

A comprehensive fund management system for NN Services & Engineering Ltd.

Features:
- Fund account and incoming fund management
- Project and expense head allocation with approval workflows
- Fund requisition and bill control (integrated with Odoo Vendor Bills)
- Inter-project/expense fund transfers
- Multi-level approval (GM → MD) with configurable rules
- Real-time computed balance tracking
- Complete audit history
- Role-based security and access control
- Dashboard and notification system
- Bank email integration (prototype)

Approval Workflow:
    Draft → Submitted → GM Approval → MD Approval → Approved / Rejected / Cancelled
    """,
    'author': 'NN Services & Engineering Ltd.',
    'website': 'https://www.nnsel.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
    ],
    'data': [
        # Security (must load before views)
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rules.xml',

        # Data
        'data/sequence_data.xml',

        # Views
        'views/menu_views.xml',
        'views/fund_account_views.xml',
        'views/fund_incoming_views.xml',
        'views/fund_allocation_views.xml',
        'views/fund_project_views.xml',
        'views/fund_expense_head_views.xml',
        'views/fund_requisition_views.xml',
        'views/account_move_views.xml',
        'views/fund_transfer_views.xml',
        'views/approval_history_views.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
