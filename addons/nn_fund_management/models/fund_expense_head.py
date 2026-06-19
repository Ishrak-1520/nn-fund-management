# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class FundExpenseHead(models.Model):
    """
    Fund Expense Head — a category of expenses that can receive allocated funds.

    Examples: Office Rent, Salary, Utility Expenses, Marketing, Administrative.

    Balance computation is identical to Fund Project — both use the same
    formula and the same set of computed fields.
    """

    _name = 'nn.fund.expense.head'
    _description = 'Expense Head'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Expense Head',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        tracking=True,
    )
    description = fields.Text(
        string='Description',
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
    active = fields.Boolean(
        string='Active',
        default=True,
    )

    # ── Related records ──────────────────────────────────────────────
    allocation_ids = fields.One2many(
        'nn.fund.allocation',
        'expense_head_id',
        string='Allocations',
    )
    requisition_ids = fields.One2many(
        'nn.fund.requisition',
        'expense_head_id',
        string='Requisitions',
    )

    # ── Computed balance fields (all store=True, readonly=True) ──────
    total_allocated = fields.Monetary(
        string='Total Allocated',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Sum of all approved allocations to this expense head.',
    )
    incoming_transfers = fields.Monetary(
        string='Incoming Transfers',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    outgoing_transfers = fields.Monetary(
        string='Outgoing Transfers',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    requisition_hold = fields.Monetary(
        string='Requisition Hold',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    transfer_hold = fields.Monetary(
        string='Transfer Hold',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    approved_unspent = fields.Monetary(
        string='Approved (Unspent)',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    total_spent = fields.Monetary(
        string='Total Spent',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    available_balance = fields.Monetary(
        string='Available Balance',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
    )

    # ══════════════════════════════════════════════════════════════════
    # COMPUTED BALANCES
    # ══════════════════════════════════════════════════════════════════

    @api.depends(
        'allocation_ids.amount',
        'allocation_ids.state',
        'requisition_ids.amount',
        'requisition_ids.state',
        'requisition_ids.total_billed',
    )
    def _compute_balances(self):
        FundTransfer = self.env['nn.fund.transfer']
        for head in self:
            # ── Total allocated ──────────────────────────────────────
            approved_allocs = head.allocation_ids.filtered(
                lambda a: a.state == 'approved'
            )
            head.total_allocated = sum(approved_allocs.mapped('amount'))

            # ── Incoming transfers ───────────────────────────────────
            in_transfers = FundTransfer.search([
                ('dest_type', '=', 'expense_head'),
                ('dest_expense_head_id', '=', head.id),
                ('state', '=', 'approved'),
            ])
            head.incoming_transfers = sum(in_transfers.mapped('amount'))

            # ── Outgoing transfers ───────────────────────────────────
            out_transfers = FundTransfer.search([
                ('source_type', '=', 'expense_head'),
                ('source_expense_head_id', '=', head.id),
                ('state', '=', 'approved'),
            ])
            head.outgoing_transfers = sum(out_transfers.mapped('amount'))

            # ── Requisition hold ─────────────────────────────────────
            pending_reqs = head.requisition_ids.filtered(
                lambda r: r.state in ('submitted', 'gm_approved')
            )
            head.requisition_hold = sum(pending_reqs.mapped('amount'))

            # ── Transfer hold ────────────────────────────────────────
            pending_out_transfers = FundTransfer.search([
                ('source_type', '=', 'expense_head'),
                ('source_expense_head_id', '=', head.id),
                ('state', 'in', ('submitted', 'gm_approved')),
            ])
            head.transfer_hold = sum(pending_out_transfers.mapped('amount'))

            # ── Approved but unspent ─────────────────────────────────
            approved_reqs = head.requisition_ids.filtered(
                lambda r: r.state in ('approved',)
            )
            head.approved_unspent = sum(
                req.amount - req.total_billed for req in approved_reqs
            )

            # ── Total spent ──────────────────────────────────────────
            head.total_spent = sum(approved_reqs.mapped('total_billed'))

            # ── Available balance ────────────────────────────────────
            head.available_balance = (
                head.total_allocated
                + head.incoming_transfers
                - head.outgoing_transfers
                - head.requisition_hold
                - head.transfer_hold
                - head.approved_unspent
                - head.total_spent
            )

    # ══════════════════════════════════════════════════════════════════
    # DISPLAY NAME
    # ══════════════════════════════════════════════════════════════════

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for head in self:
            if head.code:
                head.display_name = f"[{head.code}] {head.name}"
            else:
                head.display_name = head.name or ''
