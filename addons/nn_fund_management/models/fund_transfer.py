# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FundTransfer(models.Model):
    """
    Fund Transfer — request to move allocated funds between
    projects and/or expense heads.

    Supported transfers:
        Project → Project
        Project → Expense Head
        Expense Head → Project
        Expense Head → Expense Head

    Workflow:
        Draft → Submitted → GM Approval → MD Approval → Approved / Rejected / Cancelled

    On submission:
        - Validates source available balance (with FOR UPDATE lock)
        - Amount is deducted from source (transfer hold via computed fields)

    On approval:
        - Amount is added to destination balance (via computed fields)

    On rejection/cancellation:
        - Amount returns to source balance (via computed fields)
    """

    _name = 'nn.fund.transfer'
    _description = 'Fund Transfer'
    _inherit = ['nn.approval.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Transfer Number',
        required=True,
        readonly=True,
        default='New',
        copy=False,
    )

    # ── Source ────────────────────────────────────────────────────────
    source_type = fields.Selection(
        selection=[
            ('project', 'Project'),
            ('expense_head', 'Expense Head'),
        ],
        string='Source Type',
        required=True,
        tracking=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    source_project_id = fields.Many2one(
        'nn.fund.project',
        string='Source Project',
        tracking=True,
        index=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    source_expense_head_id = fields.Many2one(
        'nn.fund.expense.head',
        string='Source Expense Head',
        tracking=True,
        index=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )

    # ── Destination ──────────────────────────────────────────────────
    dest_type = fields.Selection(
        selection=[
            ('project', 'Project'),
            ('expense_head', 'Expense Head'),
        ],
        string='Destination Type',
        required=True,
        tracking=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    dest_project_id = fields.Many2one(
        'nn.fund.project',
        string='Destination Project',
        tracking=True,
        index=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    dest_expense_head_id = fields.Many2one(
        'nn.fund.expense.head',
        string='Destination Expense Head',
        tracking=True,
        index=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )

    # ── Transfer details ─────────────────────────────────────────────
    amount = fields.Monetary(
        string='Amount',
        required=True,
        tracking=True,
        currency_field='currency_id',
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    reason = fields.Text(
        string='Reason',
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )

    # ── Computed helper fields for display ────────────────────────────
    source_display = fields.Char(
        string='Source',
        compute='_compute_display_fields',
    )
    dest_display = fields.Char(
        string='Destination',
        compute='_compute_display_fields',
    )

    # ══════════════════════════════════════════════════════════════════
    # COMPUTED FIELDS
    # ══════════════════════════════════════════════════════════════════

    @api.depends(
        'source_type', 'source_project_id', 'source_expense_head_id',
        'dest_type', 'dest_project_id', 'dest_expense_head_id',
    )
    def _compute_display_fields(self):
        for transfer in self:
            # Source display
            if transfer.source_type == 'project' and transfer.source_project_id:
                transfer.source_display = transfer.source_project_id.display_name
            elif transfer.source_type == 'expense_head' and transfer.source_expense_head_id:
                transfer.source_display = transfer.source_expense_head_id.display_name
            else:
                transfer.source_display = ''

            # Destination display
            if transfer.dest_type == 'project' and transfer.dest_project_id:
                transfer.dest_display = transfer.dest_project_id.display_name
            elif transfer.dest_type == 'expense_head' and transfer.dest_expense_head_id:
                transfer.dest_display = transfer.dest_expense_head_id.display_name
            else:
                transfer.dest_display = ''

    # ══════════════════════════════════════════════════════════════════
    # CONSTRAINTS
    # ══════════════════════════════════════════════════════════════════

    @api.constrains('amount')
    def _check_amount_positive(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_(
                    "The transfer amount must be greater than zero."
                ))

    @api.constrains(
        'source_type', 'source_project_id', 'source_expense_head_id',
        'dest_type', 'dest_project_id', 'dest_expense_head_id',
    )
    def _check_source_destination(self):
        for record in self:
            # Validate source selection
            if record.source_type == 'project' and not record.source_project_id:
                raise ValidationError(_("Please select a source project."))
            if record.source_type == 'expense_head' and not record.source_expense_head_id:
                raise ValidationError(_("Please select a source expense head."))

            # Validate destination selection
            if record.dest_type == 'project' and not record.dest_project_id:
                raise ValidationError(_("Please select a destination project."))
            if record.dest_type == 'expense_head' and not record.dest_expense_head_id:
                raise ValidationError(_("Please select a destination expense head."))

            # Source and destination cannot be the same
            if record.source_type == record.dest_type:
                if (record.source_type == 'project'
                        and record.source_project_id == record.dest_project_id):
                    raise ValidationError(_(
                        "Source and destination cannot be the same project."
                    ))
                if (record.source_type == 'expense_head'
                        and record.source_expense_head_id == record.dest_expense_head_id):
                    raise ValidationError(_(
                        "Source and destination cannot be the same expense head."
                    ))

    # ══════════════════════════════════════════════════════════════════
    # CRUD OVERRIDES
    # ══════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'nn.fund.transfer'
                ) or 'New'
        return super().create(vals_list)

    # ══════════════════════════════════════════════════════════════════
    # ONCHANGE
    # ══════════════════════════════════════════════════════════════════

    @api.onchange('source_type')
    def _onchange_source_type(self):
        if self.source_type == 'project':
            self.source_expense_head_id = False
        elif self.source_type == 'expense_head':
            self.source_project_id = False

    @api.onchange('dest_type')
    def _onchange_dest_type(self):
        if self.dest_type == 'project':
            self.dest_expense_head_id = False
        elif self.dest_type == 'expense_head':
            self.dest_project_id = False

    # ══════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ══════════════════════════════════════════════════════════════════

    def _get_source_record(self):
        """Return the source project or expense head."""
        self.ensure_one()
        if self.source_type == 'project':
            return self.source_project_id
        return self.source_expense_head_id

    def _get_dest_record(self):
        """Return the destination project or expense head."""
        self.ensure_one()
        if self.dest_type == 'project':
            return self.dest_project_id
        return self.dest_expense_head_id

    # ══════════════════════════════════════════════════════════════════
    # APPROVAL MIXIN HOOKS
    # ══════════════════════════════════════════════════════════════════

    def _on_submit_validate(self):
        """
        Validate source has sufficient available balance.
        Acquires FOR UPDATE lock on the source record for concurrency safety.
        """
        self.ensure_one()
        source = self._get_source_record()

        # Acquire row-level lock
        self._lock_balance_record(source)

        # Re-read balance after lock
        source.invalidate_recordset(['available_balance'])
        available = source.available_balance

        if self.amount > available:
            raise UserError(_(
                "Insufficient available balance in source '%(source)s'. "
                "Available: %(available)s, Requested: %(requested)s.",
                source=source.display_name,
                available=available,
                requested=self.amount,
            ))

    def _on_submit_hold(self):
        """Hold is implicit via computed fields (transfer_hold)."""
        pass

    def _on_approval_complete(self):
        """
        Approval complete — destination balance increases automatically
        via the computed fields on the destination project/expense head
        (incoming_transfers).
        """
        pass

    def _on_rejection(self):
        """Release — computed fields remove the transfer_hold."""
        pass

    def _on_cancellation(self):
        """Release — computed fields remove the transfer_hold."""
        pass

    # ══════════════════════════════════════════════════════════════════
    # AUDIT HISTORY HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _get_approval_amount(self):
        self.ensure_one()
        return self.amount

    def _get_project(self):
        self.ensure_one()
        return self.source_project_id or self.dest_project_id

    def _get_expense_head(self):
        self.ensure_one()
        return self.source_expense_head_id or self.dest_expense_head_id
