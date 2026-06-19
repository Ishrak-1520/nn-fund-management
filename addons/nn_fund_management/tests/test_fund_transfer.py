# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestFundTransfer(TransactionCase):
    """Test suite for Fund Transfer workflow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.finance_group = cls.env.ref('nn_fund_management.group_finance_user')
        cls.gm_group = cls.env.ref('nn_fund_management.group_gm_approver')
        cls.md_group = cls.env.ref('nn_fund_management.group_md_approver')
        cls.fund_user_group = cls.env.ref('nn_fund_management.group_fund_user')

        cls.fund_user = cls.env['res.users'].create({
            'name': 'Fund Xfer', 'login': 'fund_xfer',
            'email': 'xfer@test.com',
            'groups_id': [(4, cls.fund_user_group.id)],
        })
        cls.finance_user = cls.env['res.users'].create({
            'name': 'Finance Xfer', 'login': 'fin_xfer',
            'email': 'fin_xfer@test.com',
            'groups_id': [(4, cls.finance_group.id)],
        })
        cls.gm_user = cls.env['res.users'].create({
            'name': 'GM Xfer', 'login': 'gm_xfer',
            'email': 'gm_xfer@test.com',
            'groups_id': [(4, cls.gm_group.id)],
        })
        cls.md_user = cls.env['res.users'].create({
            'name': 'MD Xfer', 'login': 'md_xfer',
            'email': 'md_xfer@test.com',
            'groups_id': [(4, cls.md_group.id)],
        })

        # Setup: 1M in account, 600K to Project A, 200K to Project B
        cls.fund_account = cls.env['nn.fund.account'].create({
            'name': 'Xfer Account', 'account_type': 'bank',
        })
        incoming = cls.env['nn.fund.incoming'].create({
            'fund_account_id': cls.fund_account.id, 'amount': 1000000,
        })
        incoming.with_user(cls.finance_user).action_confirm()

        cls.project_a = cls.env['nn.fund.project'].create({
            'name': 'Transfer Project A', 'code': 'TPA',
        })
        cls.project_b = cls.env['nn.fund.project'].create({
            'name': 'Transfer Project B', 'code': 'TPB',
        })
        cls.expense_head = cls.env['nn.fund.expense.head'].create({
            'name': 'Transfer Expense', 'code': 'TXE',
        })

        for proj, amt in [(cls.project_a, 600000), (cls.project_b, 200000)]:
            alloc = cls.env['nn.fund.allocation'].create({
                'fund_account_id': cls.fund_account.id,
                'allocation_type': 'project',
                'project_id': proj.id,
                'amount': amt,
                'requested_by': cls.fund_user.id,
            })
            alloc.with_user(cls.fund_user).action_submit()
            alloc.with_user(cls.gm_user).action_gm_approve()
            alloc.with_user(cls.md_user).action_md_approve()

    def test_01_transfer_project_to_project(self):
        """Test transferring funds between projects (demo steps 6-8)."""
        transfer = self.env['nn.fund.transfer'].create({
            'source_type': 'project',
            'source_project_id': self.project_a.id,
            'dest_type': 'project',
            'dest_project_id': self.project_b.id,
            'amount': 200000,
            'reason': 'Redistribute funds',
            'requested_by': self.fund_user.id,
        })

        # Submit — transfer hold on source
        transfer.with_user(self.fund_user).action_submit()
        self.project_a.invalidate_recordset()
        self.assertEqual(self.project_a.transfer_hold, 200000)

        # GM Approve
        transfer.with_user(self.gm_user).action_gm_approve()

        # MD Approve — transfer completes
        transfer.with_user(self.md_user).action_md_approve()
        self.assertEqual(transfer.state, 'approved')

        # Project A: 600K - 200K transferred = 400K
        self.project_a.invalidate_recordset()
        self.assertEqual(self.project_a.outgoing_transfers, 200000)

        # Project B: 200K + 200K incoming = 400K
        self.project_b.invalidate_recordset()
        self.assertEqual(self.project_b.incoming_transfers, 200000)

    def test_02_same_source_destination_blocked(self):
        """Test that source and destination cannot be the same."""
        with self.assertRaises(ValidationError):
            self.env['nn.fund.transfer'].create({
                'source_type': 'project',
                'source_project_id': self.project_a.id,
                'dest_type': 'project',
                'dest_project_id': self.project_a.id,  # Same!
                'amount': 100000,
                'requested_by': self.fund_user.id,
            })

    def test_03_over_transfer_blocked(self):
        """Test that transferring more than available is blocked."""
        transfer = self.env['nn.fund.transfer'].create({
            'source_type': 'project',
            'source_project_id': self.project_b.id,
            'dest_type': 'project',
            'dest_project_id': self.project_a.id,
            'amount': 9999999,  # Way more than available
            'requested_by': self.fund_user.id,
        })
        with self.assertRaises(UserError):
            transfer.with_user(self.fund_user).action_submit()

    def test_04_rejection_releases_transfer_hold(self):
        """Test that rejecting releases the transfer hold."""
        self.project_a.invalidate_recordset()
        initial_available = self.project_a.available_balance

        transfer = self.env['nn.fund.transfer'].create({
            'source_type': 'project',
            'source_project_id': self.project_a.id,
            'dest_type': 'project',
            'dest_project_id': self.project_b.id,
            'amount': 50000,
            'requested_by': self.fund_user.id,
        })
        transfer.with_user(self.fund_user).action_submit()

        # Hold reduces available
        self.project_a.invalidate_recordset()
        self.assertEqual(
            self.project_a.available_balance,
            initial_available - 50000
        )

        # Reject → hold released
        transfer.with_user(self.gm_user).action_gm_reject()
        self.project_a.invalidate_recordset()
        self.assertEqual(self.project_a.available_balance, initial_available)

    def test_05_project_to_expense_head(self):
        """Test transfer from project to expense head."""
        transfer = self.env['nn.fund.transfer'].create({
            'source_type': 'project',
            'source_project_id': self.project_a.id,
            'dest_type': 'expense_head',
            'dest_expense_head_id': self.expense_head.id,
            'amount': 100000,
            'requested_by': self.fund_user.id,
        })
        transfer.with_user(self.fund_user).action_submit()
        transfer.with_user(self.gm_user).action_gm_approve()
        transfer.with_user(self.md_user).action_md_approve()

        self.expense_head.invalidate_recordset()
        self.assertEqual(self.expense_head.incoming_transfers, 100000)
