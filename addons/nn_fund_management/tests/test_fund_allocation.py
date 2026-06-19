# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestFundAllocation(TransactionCase):
    """Test suite for Fund Allocation workflow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Create security groups
        cls.fund_user_group = cls.env.ref('nn_fund_management.group_fund_user')
        cls.finance_group = cls.env.ref('nn_fund_management.group_finance_user')
        cls.gm_group = cls.env.ref('nn_fund_management.group_gm_approver')
        cls.md_group = cls.env.ref('nn_fund_management.group_md_approver')
        cls.admin_group = cls.env.ref('nn_fund_management.group_fund_administrator')

        # Create users
        cls.fund_user = cls.env['res.users'].create({
            'name': 'Fund User',
            'login': 'fund_user_test',
            'email': 'fund@test.com',
            'groups_id': [(4, cls.fund_user_group.id)],
        })
        cls.finance_user = cls.env['res.users'].create({
            'name': 'Finance User',
            'login': 'finance_alloc_test',
            'email': 'finance_alloc@test.com',
            'groups_id': [(4, cls.finance_group.id)],
        })
        cls.gm_user = cls.env['res.users'].create({
            'name': 'GM User',
            'login': 'gm_test',
            'email': 'gm@test.com',
            'groups_id': [(4, cls.gm_group.id)],
        })
        cls.md_user = cls.env['res.users'].create({
            'name': 'MD User',
            'login': 'md_test',
            'email': 'md@test.com',
            'groups_id': [(4, cls.md_group.id)],
        })

        # Create fund account with money
        cls.fund_account = cls.env['nn.fund.account'].create({
            'name': 'Main Account',
            'account_type': 'bank',
        })
        incoming = cls.env['nn.fund.incoming'].create({
            'fund_account_id': cls.fund_account.id,
            'amount': 1000000,
            'transaction_reference': 'INIT-001',
        })
        incoming.with_user(cls.finance_user).action_confirm()

        # Create project and expense head
        cls.project_a = cls.env['nn.fund.project'].create({
            'name': 'Project A',
            'code': 'PA',
        })
        cls.expense_rent = cls.env['nn.fund.expense.head'].create({
            'name': 'Office Rent',
            'code': 'RENT',
        })

    def _create_allocation(self, amount=600000, target='project'):
        """Helper to create an allocation request."""
        vals = {
            'fund_account_id': self.fund_account.id,
            'allocation_type': target,
            'amount': amount,
            'purpose': 'Test allocation',
            'requested_by': self.fund_user.id,
        }
        if target == 'project':
            vals['project_id'] = self.project_a.id
        else:
            vals['expense_head_id'] = self.expense_rent.id
        return self.env['nn.fund.allocation'].with_user(self.fund_user).create(vals)

    def test_01_allocation_full_workflow(self):
        """Test the complete allocation approval workflow."""
        alloc = self._create_allocation(amount=400000)
        self.assertEqual(alloc.state, 'draft')

        # Submit
        alloc.with_user(self.fund_user).action_submit()
        self.assertEqual(alloc.state, 'submitted')

        # Verify hold on fund account
        self.fund_account.invalidate_recordset()
        self.assertEqual(self.fund_account.amount_on_hold, 400000)

        # GM Approve
        alloc.with_user(self.gm_user).action_gm_approve()
        self.assertEqual(alloc.state, 'gm_approved')

        # MD Approve
        alloc.with_user(self.md_user).action_md_approve()
        self.assertEqual(alloc.state, 'approved')

        # Verify balances
        self.fund_account.invalidate_recordset()
        self.assertEqual(self.fund_account.total_assigned, 400000)
        self.assertEqual(self.fund_account.amount_on_hold, 0)
        self.assertEqual(self.fund_account.unassigned_balance, 600000)

        # Verify project balance
        self.project_a.invalidate_recordset()
        self.assertEqual(self.project_a.total_allocated, 400000)
        self.assertEqual(self.project_a.available_balance, 400000)

    def test_02_allocation_rejection_releases_hold(self):
        """Test that rejecting an allocation returns funds to unassigned."""
        self.fund_account.invalidate_recordset()
        initial_unassigned = self.fund_account.unassigned_balance

        alloc = self._create_allocation(amount=200000)
        alloc.with_user(self.fund_user).action_submit()

        # Verify hold
        self.fund_account.invalidate_recordset()
        self.assertEqual(
            self.fund_account.unassigned_balance,
            initial_unassigned - 200000
        )

        # GM Reject
        alloc.with_user(self.gm_user).action_gm_reject()
        self.assertEqual(alloc.state, 'rejected')

        # Verify release
        self.fund_account.invalidate_recordset()
        self.assertEqual(self.fund_account.unassigned_balance, initial_unassigned)

    def test_03_over_allocation_blocked(self):
        """Test that allocating more than available is blocked."""
        alloc = self._create_allocation(amount=2000000)  # More than available
        with self.assertRaises(UserError):
            alloc.with_user(self.fund_user).action_submit()

    def test_04_must_select_project_or_expense(self):
        """Test that allocation must target project or expense head."""
        with self.assertRaises(ValidationError):
            self.env['nn.fund.allocation'].create({
                'fund_account_id': self.fund_account.id,
                'allocation_type': 'project',
                # Missing project_id
                'amount': 100000,
            })

    def test_05_allocation_to_expense_head(self):
        """Test allocation to an expense head works correctly."""
        alloc = self._create_allocation(amount=100000, target='expense_head')
        alloc.with_user(self.fund_user).action_submit()
        alloc.with_user(self.gm_user).action_gm_approve()
        alloc.with_user(self.md_user).action_md_approve()

        self.expense_rent.invalidate_recordset()
        self.assertEqual(self.expense_rent.total_allocated, 100000)
        self.assertEqual(self.expense_rent.available_balance, 100000)

    def test_06_gm_must_approve_before_md(self):
        """Test that MD cannot approve before GM."""
        alloc = self._create_allocation(amount=100000)
        alloc.with_user(self.fund_user).action_submit()

        with self.assertRaises(UserError):
            alloc.with_user(self.md_user).action_md_approve()

    def test_07_non_gm_cannot_approve(self):
        """Test that non-GM users cannot GM-approve."""
        alloc = self._create_allocation(amount=100000)
        alloc.with_user(self.fund_user).action_submit()

        with self.assertRaises(UserError):
            alloc.with_user(self.fund_user).action_gm_approve()

    def test_08_approval_history_created(self):
        """Test that approval history records are created."""
        alloc = self._create_allocation(amount=100000)
        alloc.with_user(self.fund_user).action_submit()

        history = self.env['nn.approval.history'].search([
            ('res_model', '=', 'nn.fund.allocation'),
            ('res_id', '=', alloc.id),
        ])
        self.assertTrue(len(history) >= 1)
        self.assertEqual(history[0].action, 'submit')

    def test_09_cannot_delete_non_draft(self):
        """Test that submitted allocations cannot be deleted."""
        alloc = self._create_allocation(amount=100000)
        alloc.with_user(self.fund_user).action_submit()

        with self.assertRaises(UserError):
            alloc.unlink()

    def test_10_reset_to_draft_after_rejection(self):
        """Test that rejected allocations can be reset to draft."""
        alloc = self._create_allocation(amount=100000)
        alloc.with_user(self.fund_user).action_submit()
        alloc.with_user(self.gm_user).action_gm_reject()

        alloc.with_user(self.fund_user).action_reset_to_draft()
        self.assertEqual(alloc.state, 'draft')
