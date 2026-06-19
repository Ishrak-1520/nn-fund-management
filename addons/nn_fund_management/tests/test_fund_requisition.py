# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestFundRequisition(TransactionCase):
    """Test suite for Fund Requisition workflow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.finance_group = cls.env.ref('nn_fund_management.group_finance_user')
        cls.gm_group = cls.env.ref('nn_fund_management.group_gm_approver')
        cls.md_group = cls.env.ref('nn_fund_management.group_md_approver')
        cls.fund_user_group = cls.env.ref('nn_fund_management.group_fund_user')

        cls.fund_user = cls.env['res.users'].create({
            'name': 'Fund User Req',
            'login': 'fund_req_test',
            'email': 'fund_req@test.com',
            'groups_id': [(4, cls.fund_user_group.id)],
        })
        cls.finance_user = cls.env['res.users'].create({
            'name': 'Finance Req',
            'login': 'finance_req_test',
            'email': 'finance_req@test.com',
            'groups_id': [(4, cls.finance_group.id)],
        })
        cls.gm_user = cls.env['res.users'].create({
            'name': 'GM Req',
            'login': 'gm_req_test',
            'email': 'gm_req@test.com',
            'groups_id': [(4, cls.gm_group.id)],
        })
        cls.md_user = cls.env['res.users'].create({
            'name': 'MD Req',
            'login': 'md_req_test',
            'email': 'md_req@test.com',
            'groups_id': [(4, cls.md_group.id)],
        })

        # Set up fund account with 1,000,000
        cls.fund_account = cls.env['nn.fund.account'].create({
            'name': 'Req Test Account', 'account_type': 'bank',
        })
        incoming = cls.env['nn.fund.incoming'].create({
            'fund_account_id': cls.fund_account.id,
            'amount': 1000000,
        })
        incoming.with_user(cls.finance_user).action_confirm()

        # Create and fully approve a 600,000 allocation to Project B
        cls.project_b = cls.env['nn.fund.project'].create({
            'name': 'Project B', 'code': 'PB',
        })
        alloc = cls.env['nn.fund.allocation'].create({
            'fund_account_id': cls.fund_account.id,
            'allocation_type': 'project',
            'project_id': cls.project_b.id,
            'amount': 600000,
            'requested_by': cls.fund_user.id,
        })
        alloc.with_user(cls.fund_user).action_submit()
        alloc.with_user(cls.gm_user).action_gm_approve()
        alloc.with_user(cls.md_user).action_md_approve()

    def _create_requisition(self, amount=150000, project=None):
        """Helper to create a requisition."""
        project = project or self.project_b
        return self.env['nn.fund.requisition'].create({
            'allocation_type': 'project',
            'project_id': project.id,
            'amount': amount,
            'purpose': 'Test requisition',
            'requested_by': self.fund_user.id,
        })

    def _approve_requisition(self, req):
        """Helper to fully approve a requisition."""
        req.with_user(self.fund_user).action_submit()
        req.with_user(self.gm_user).action_gm_approve()
        req.with_user(self.md_user).action_md_approve()

    def test_01_requisition_full_workflow(self):
        """Test complete requisition approval workflow."""
        req = self._create_requisition(amount=150000)
        self._approve_requisition(req)
        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.remaining_billable, 150000)

    def test_02_requisition_hold_on_submit(self):
        """Test that submitting places funds on hold."""
        req = self._create_requisition(amount=100000)
        req.with_user(self.fund_user).action_submit()

        self.project_b.invalidate_recordset()
        self.assertGreater(self.project_b.requisition_hold, 0)

    def test_03_over_requisition_blocked(self):
        """Test that requesting more than available is blocked."""
        req = self._create_requisition(amount=9999999)
        with self.assertRaises(UserError):
            req.with_user(self.fund_user).action_submit()

    def test_04_close_requisition_releases_remainder(self):
        """Test that closing releases unused billable amount."""
        req = self._create_requisition(amount=200000)
        self._approve_requisition(req)

        # Close without any bills → full amount released
        req.action_close()
        self.assertEqual(req.state, 'closed')

    def test_05_auto_sequence(self):
        """Test requisition auto-numbering."""
        req = self._create_requisition()
        self.assertIn('FR/', req.name)
