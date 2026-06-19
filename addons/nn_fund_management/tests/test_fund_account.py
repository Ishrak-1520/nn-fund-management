# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestFundAccount(TransactionCase):
    """Test suite for Fund Account and Incoming Fund models."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Create a finance user
        cls.finance_group = cls.env.ref('nn_fund_management.group_finance_user')
        cls.admin_group = cls.env.ref('nn_fund_management.group_fund_administrator')

        cls.finance_user = cls.env['res.users'].create({
            'name': 'Finance User',
            'login': 'finance_test',
            'email': 'finance@test.com',
            'groups_id': [(4, cls.finance_group.id)],
        })

        cls.admin_user = cls.env['res.users'].create({
            'name': 'Admin User',
            'login': 'admin_test',
            'email': 'admin@test.com',
            'groups_id': [(4, cls.admin_group.id)],
        })

        # Create a fund account
        cls.fund_account = cls.env['nn.fund.account'].create({
            'name': 'Test Bank Account',
            'code': 'TBA',
            'account_type': 'bank',
        })

    def _create_incoming(self, amount=1000000, ref=None):
        """Helper to create an incoming fund record."""
        return self.env['nn.fund.incoming'].create({
            'fund_account_id': self.fund_account.id,
            'amount': amount,
            'transaction_reference': ref or False,
            'sender': 'Test Sender',
        })

    def test_01_create_fund_account(self):
        """Test basic fund account creation."""
        self.assertEqual(self.fund_account.total_received, 0)
        self.assertEqual(self.fund_account.unassigned_balance, 0)
        self.assertEqual(self.fund_account.amount_on_hold, 0)
        self.assertEqual(self.fund_account.total_assigned, 0)

    def test_02_incoming_fund_confirm(self):
        """Test that confirming an incoming fund updates the account balance."""
        incoming = self._create_incoming(amount=500000)
        self.assertEqual(incoming.state, 'draft')
        self.assertEqual(self.fund_account.total_received, 0)

        # Confirm as finance user
        incoming.with_user(self.finance_user).action_confirm()
        self.assertEqual(incoming.state, 'confirmed')

        # Balance should update
        self.fund_account.invalidate_recordset()
        self.assertEqual(self.fund_account.total_received, 500000)
        self.assertEqual(self.fund_account.unassigned_balance, 500000)

    def test_03_incoming_fund_cancel(self):
        """Test that cancelling an incoming fund restores the balance."""
        incoming = self._create_incoming(amount=300000)
        incoming.with_user(self.finance_user).action_confirm()

        self.fund_account.invalidate_recordset()
        initial_balance = self.fund_account.unassigned_balance

        # Cancel as admin
        incoming.with_user(self.admin_user).action_cancel()
        self.assertEqual(incoming.state, 'cancelled')

        self.fund_account.invalidate_recordset()
        self.assertEqual(
            self.fund_account.unassigned_balance,
            initial_balance - 300000
        )

    def test_04_duplicate_transaction_reference(self):
        """Test that duplicate transaction references are blocked."""
        self._create_incoming(ref='TXN-001')
        with self.assertRaises(Exception):
            # Should fail due to SQL unique constraint
            self._create_incoming(ref='TXN-001')

    def test_05_positive_amount_required(self):
        """Test that zero or negative amounts are rejected."""
        with self.assertRaises(ValidationError):
            self._create_incoming(amount=0)

        with self.assertRaises(ValidationError):
            self._create_incoming(amount=-100)

    def test_06_cannot_delete_confirmed(self):
        """Test that confirmed incoming funds cannot be deleted."""
        incoming = self._create_incoming(amount=100000)
        incoming.with_user(self.finance_user).action_confirm()

        with self.assertRaises(UserError):
            incoming.unlink()

    def test_07_auto_sequence(self):
        """Test that incoming funds get auto-numbered."""
        incoming = self._create_incoming()
        self.assertNotEqual(incoming.name, 'New')
        self.assertIn('FIN/', incoming.name)

    def test_08_non_finance_user_cannot_confirm(self):
        """Test that non-finance users cannot confirm incoming funds."""
        fund_user_group = self.env.ref('nn_fund_management.group_fund_user')
        regular_user = self.env['res.users'].create({
            'name': 'Regular User',
            'login': 'regular_test',
            'email': 'regular@test.com',
            'groups_id': [(4, fund_user_group.id)],
        })

        incoming = self._create_incoming()
        with self.assertRaises(UserError):
            incoming.with_user(regular_user).action_confirm()
