# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FundAllocation(models.Model):
    """
    Fund Allocation — request to move funds from a fund account's
    unassigned balance to a specific project or expense head.

    Inherits the approval mixin for the standard workflow:
        Draft → Submitted → GM Approval → MD Approval → Approved / Rejected / Cancelled

    On submission:
        - Validates available unassigned balance (with FOR UPDATE lock)
        - Deducts amount from unassigned balance (places on hold)

    On approval:
        - Moves amount from hold → project/expense head balance

    On rejection/cancellation:
        - Returns held amount to unassigned balance
    """

    _name = 'nn.fund.allocation'
    _description = 'Fund Allocation'
    _inherit = ['nn.approval.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Request Number',
        required=True,
        readonly=True,
        default='New',
        copy=False,
    )
    fund_account_id = fields.Many2one(
        'nn.fund.account',
        string='Fund Account',
        required=True,
        tracking=True,
        index=True,
    )
    allocation_type = fields.Selection(
        selection=[
            ('project', 'Project'),
            ('expense_head', 'Expense Head'),
        ],
        string='Allocate To',
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        'nn.fund.project',
        string='Project',
        tracking=True,
        index=True,
    )
    expense_head_id = fields.Many2one(
        'nn.fund.expense.head',
        string='Expense Head',
        tracking=True,
        index=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        tracking=True,
        currency_field='currency_id',
    )
    purpose = fields.Text(
        string='Purpose',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'nn_fund_allocation_attachment_rel',
        'allocation_id',
        'attachment_id',
        string='Attachments',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='fund_account_id.currency_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='fund_account_id.company_id',
        store=True,
        readonly=True,
    )

    # ══════════════════════════════════════════════════════════════════
    # CONSTRAINTS
    # ══════════════════════════════════════════════════════════════════

    @api.constrains('amount')
    def _check_amount_positive(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_(
                    "The allocation amount must be greater than zero."
                ))

    @api.constrains('allocation_type', 'project_id', 'expense_head_id')
    def _check_allocation_target(self):
        for record in self:
            if record.allocation_type == 'project' and not record.project_id:
                raise ValidationError(_(
                    "Please select a project for the allocation."
                ))
            if record.allocation_type == 'expense_head' and not record.expense_head_id:
                raise ValidationError(_(
                    "Please select an expense head for the allocation."
                ))
            if record.project_id and record.expense_head_id:
                raise ValidationError(_(
                    "An allocation must use either a project or an expense head, not both."
                ))

    # ══════════════════════════════════════════════════════════════════
    # CRUD OVERRIDES
    # ══════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'nn.fund.allocation'
                ) or 'New'
        return super().create(vals_list)

    # ══════════════════════════════════════════════════════════════════
    # ONCHANGE
    # ══════════════════════════════════════════════════════════════════

    @api.onchange('allocation_type')
    def _onchange_allocation_type(self):
        """Clear the non-selected target when allocation type changes."""
        if self.allocation_type == 'project':
            self.expense_head_id = False
        elif self.allocation_type == 'expense_head':
            self.project_id = False

    # ══════════════════════════════════════════════════════════════════
    # APPROVAL MIXIN HOOKS
    # ══════════════════════════════════════════════════════════════════

    def _on_submit_validate(self):
        """
        Validate that the fund account has sufficient unassigned balance.
        Acquires a FOR UPDATE lock on the fund account to prevent
        concurrent allocation requests from racing.
        """
        self.ensure_one()

        # Acquire row-level lock on the fund account
        self._lock_balance_record(self.fund_account_id)

        # Re-read the balance after acquiring the lock
        self.fund_account_id.invalidate_recordset(['unassigned_balance'])
        available = self.fund_account_id.unassigned_balance

        if self.amount > available:
            raise UserError(_(
                "Insufficient unassigned balance in fund account '%(account)s'. "
                "Available: %(available)s, Requested: %(requested)s.",
                account=self.fund_account_id.display_name,
                available=available,
                requested=self.amount,
            ))

    def _on_submit_hold(self):
        """
        The hold is implicit through the computed field on nn.fund.account.
        When the allocation state changes to 'submitted', the fund account's
        _compute_balances will automatically pick it up as a pending allocation,
        increasing amount_on_hold and decreasing unassigned_balance.
        """
        pass  # Handled by computed fields

    def _on_approval_complete(self):
        """
        When the allocation is approved (MD approval), the computed fields
        on both the fund account and the target project/expense head
        automatically update:
        - Fund account: moves from on_hold → assigned
        - Project/expense head: increases total_allocated
        """
        pass  # Handled by computed fields

    def _on_rejection(self):
        """
        When rejected, the state changes to 'rejected', and computed fields
        automatically remove the hold (since 'rejected' is not in the
        pending states list).
        """
        pass  # Handled by computed fields

    def _on_cancellation(self):
        """
        Same as rejection — the computed fields handle the release
        when the state moves out of pending/approved states.
        """
        pass  # Handled by computed fields

    # ══════════════════════════════════════════════════════════════════
    # AUDIT HISTORY HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _get_approval_amount(self):
        self.ensure_one()
        return self.amount

    def _get_fund_account(self):
        self.ensure_one()
        return self.fund_account_id

    def _get_project(self):
        self.ensure_one()
        return self.project_id

    def _get_expense_head(self):
        self.ensure_one()
        return self.expense_head_id
