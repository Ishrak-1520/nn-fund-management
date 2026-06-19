# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FundRequisition(models.Model):
    """
    Fund Requisition — request to spend funds from a project or expense head.

    Workflow:
        Draft → Submitted → GM Approval → MD Approval → Approved → Closed
        (can also be Rejected or Cancelled from pending states)

    Bills (Odoo Vendor Bills) are linked to approved requisitions.
    The remaining_billable amount tracks how much can still be billed.
    """

    _name = 'nn.fund.requisition'
    _description = 'Fund Requisition'
    _inherit = ['nn.approval.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'
    _rec_name = 'name'

    # Override state to add 'closed'
    state = fields.Selection(
        selection_add=[
            ('closed', 'Closed'),
        ],
        ondelete={'closed': 'set default'},
    )

    name = fields.Char(
        string='Requisition Number',
        required=True,
        readonly=True,
        default='New',
        copy=False,
    )
    allocation_type = fields.Selection(
        selection=[
            ('project', 'Project'),
            ('expense_head', 'Expense Head'),
        ],
        string='Requisition For',
        required=True,
        tracking=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    project_id = fields.Many2one(
        'nn.fund.project',
        string='Project',
        tracking=True,
        index=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    expense_head_id = fields.Many2one(
        'nn.fund.expense.head',
        string='Expense Head',
        tracking=True,
        index=True,
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    amount = fields.Monetary(
        string='Requested Amount',
        required=True,
        tracking=True,
        currency_field='currency_id',
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    purpose = fields.Text(
        string='Purpose',
        states={'draft': [('readonly', False)]},
        readonly=True,
    )
    required_date = fields.Date(
        string='Required Date',
        states={'draft': [('readonly', False)]},
        readonly=True,
        help='Date by which the funds are needed.',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'nn_fund_requisition_attachment_rel',
        'requisition_id',
        'attachment_id',
        string='Attachments',
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

    # ── Bill tracking ────────────────────────────────────────────────
    bill_ids = fields.One2many(
        'account.move',
        'fund_requisition_id',
        string='Bills',
        domain=[('move_type', '=', 'in_invoice')],
    )
    total_billed = fields.Monetary(
        string='Total Billed',
        compute='_compute_bill_amounts',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Sum of all posted bills against this requisition.',
    )
    remaining_billable = fields.Monetary(
        string='Remaining Billable',
        compute='_compute_bill_amounts',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Amount that can still be billed: Approved Amount − Total Billed.',
    )
    bill_count = fields.Integer(
        string='Bill Count',
        compute='_compute_bill_amounts',
    )

    # ══════════════════════════════════════════════════════════════════
    # COMPUTED FIELDS
    # ══════════════════════════════════════════════════════════════════

    @api.depends('bill_ids.state', 'bill_ids.amount_total_signed', 'amount')
    def _compute_bill_amounts(self):
        for req in self:
            posted_bills = req.bill_ids.filtered(
                lambda b: b.state == 'posted'
            )
            # amount_total_signed is negative for vendor bills in Odoo,
            # so we use the absolute value
            req.total_billed = sum(abs(b.amount_total_signed) for b in posted_bills)
            req.remaining_billable = req.amount - req.total_billed
            req.bill_count = len(req.bill_ids)

    # ══════════════════════════════════════════════════════════════════
    # CONSTRAINTS
    # ══════════════════════════════════════════════════════════════════

    @api.constrains('amount')
    def _check_amount_positive(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_(
                    "The requisition amount must be greater than zero."
                ))

    @api.constrains('allocation_type', 'project_id', 'expense_head_id')
    def _check_requisition_target(self):
        for record in self:
            if record.allocation_type == 'project' and not record.project_id:
                raise ValidationError(_(
                    "Please select a project for the requisition."
                ))
            if record.allocation_type == 'expense_head' and not record.expense_head_id:
                raise ValidationError(_(
                    "Please select an expense head for the requisition."
                ))
            if record.project_id and record.expense_head_id:
                raise ValidationError(_(
                    "A requisition must use either a project or an expense head, not both."
                ))

    # ══════════════════════════════════════════════════════════════════
    # CRUD OVERRIDES
    # ══════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'nn.fund.requisition'
                ) or 'New'
        return super().create(vals_list)

    # ══════════════════════════════════════════════════════════════════
    # ONCHANGE
    # ══════════════════════════════════════════════════════════════════

    @api.onchange('allocation_type')
    def _onchange_allocation_type(self):
        if self.allocation_type == 'project':
            self.expense_head_id = False
        elif self.allocation_type == 'expense_head':
            self.project_id = False

    # ══════════════════════════════════════════════════════════════════
    # APPROVAL MIXIN HOOKS
    # ══════════════════════════════════════════════════════════════════

    def _get_balance_record(self):
        """Return the project or expense head whose balance should be locked."""
        self.ensure_one()
        if self.allocation_type == 'project':
            return self.project_id
        return self.expense_head_id

    def _on_submit_validate(self):
        """
        Validate that the project/expense head has sufficient available balance.
        Acquires FOR UPDATE lock for concurrency safety.
        """
        self.ensure_one()
        balance_record = self._get_balance_record()

        # Acquire row-level lock
        self._lock_balance_record(balance_record)

        # Re-read balance after lock
        balance_record.invalidate_recordset(['available_balance'])
        available = balance_record.available_balance

        if self.amount > available:
            raise UserError(_(
                "Insufficient available balance in '%(target)s'. "
                "Available: %(available)s, Requested: %(requested)s.",
                target=balance_record.display_name,
                available=available,
                requested=self.amount,
            ))

    def _on_submit_hold(self):
        """Hold is implicit via computed fields (requisition_hold)."""
        pass

    def _on_approval_complete(self):
        """Approved — amount stays reserved for bills (approved_unspent)."""
        pass

    def _on_rejection(self):
        """Rejection — computed fields release the hold."""
        pass

    def _on_cancellation(self):
        """Cancellation — computed fields release the hold."""
        pass

    # ══════════════════════════════════════════════════════════════════
    # ADDITIONAL ACTIONS
    # ══════════════════════════════════════════════════════════════════

    def action_close(self):
        """
        Close the requisition, releasing any unused billable amount
        back to the project/expense head's available balance.
        """
        for record in self:
            if record.state != 'approved':
                raise UserError(_(
                    "Only approved requisitions can be closed."
                ))

            record._create_approval_history(
                action='close',
                new_state='closed',
                amount=record.remaining_billable,
                comment=f"Closed with {record.remaining_billable} remaining (released).",
                project_id=record.project_id and record.project_id.id,
                expense_head_id=record.expense_head_id and record.expense_head_id.id,
                reference=record.display_name,
            )

            record.write({'state': 'closed'})

    def action_view_bills(self):
        """Open the list of bills linked to this requisition."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bills'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [
                ('fund_requisition_id', '=', self.id),
                ('move_type', '=', 'in_invoice'),
            ],
            'context': {
                'default_move_type': 'in_invoice',
                'default_fund_requisition_id': self.id,
            },
        }

    # ══════════════════════════════════════════════════════════════════
    # AUDIT HISTORY HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _get_approval_amount(self):
        self.ensure_one()
        return self.amount

    def _get_project(self):
        self.ensure_one()
        return self.project_id

    def _get_expense_head(self):
        self.ensure_one()
        return self.expense_head_id
