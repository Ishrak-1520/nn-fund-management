# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FundAccount(models.Model):
    """
    Fund Account — represents a bank account, cash register, or other
    financial account that receives incoming funds.

    Displays computed balance summaries:
    - Total received: sum of all confirmed incoming funds
    - Unassigned balance: available for allocation
    - Amount on hold: reserved by pending allocation requests
    - Total assigned: allocated to projects/expense heads
    """

    _name = 'nn.fund.account'
    _description = 'Fund Account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Account Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        tracking=True,
    )
    account_type = fields.Selection(
        selection=[
            ('bank', 'Bank'),
            ('cash', 'Cash'),
            ('other', 'Other'),
        ],
        string='Account Type',
        required=True,
        default='bank',
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
    incoming_fund_ids = fields.One2many(
        'nn.fund.incoming',
        'fund_account_id',
        string='Incoming Funds',
    )
    allocation_ids = fields.One2many(
        'nn.fund.allocation',
        'fund_account_id',
        string='Allocations',
    )

    # ── Computed balance fields (store=True, readonly=True) ──────────
    total_received = fields.Monetary(
        string='Total Received',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        tracking=True,
        help='Sum of all confirmed incoming funds.',
    )
    total_assigned = fields.Monetary(
        string='Total Assigned',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        tracking=True,
        help='Total amount allocated to projects and expense heads.',
    )
    amount_on_hold = fields.Monetary(
        string='Amount on Hold',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        tracking=True,
        help='Amount reserved by pending allocation requests.',
    )
    unassigned_balance = fields.Monetary(
        string='Unassigned Balance',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        tracking=True,
        help='Available for new allocations: Total Received − Assigned − On Hold.',
    )

    # ── Smart button counts ──────────────────────────────────────────
    incoming_fund_count = fields.Integer(
        string='Incoming Funds',
        compute='_compute_counts',
    )
    allocation_count = fields.Integer(
        string='Allocations',
        compute='_compute_counts',
    )

    # ══════════════════════════════════════════════════════════════════
    # COMPUTED FIELDS
    # ══════════════════════════════════════════════════════════════════

    @api.depends(
        'incoming_fund_ids.amount',
        'incoming_fund_ids.state',
        'allocation_ids.amount',
        'allocation_ids.state',
    )
    def _compute_balances(self):
        for account in self:
            # Total received = sum of confirmed incoming funds
            confirmed_funds = account.incoming_fund_ids.filtered(
                lambda f: f.state == 'confirmed'
            )
            account.total_received = sum(confirmed_funds.mapped('amount'))

            # Approved allocations → assigned
            approved_allocations = account.allocation_ids.filtered(
                lambda a: a.state == 'approved'
            )
            account.total_assigned = sum(approved_allocations.mapped('amount'))

            # Pending allocations (submitted or gm_approved) → on hold
            pending_allocations = account.allocation_ids.filtered(
                lambda a: a.state in ('submitted', 'gm_approved')
            )
            account.amount_on_hold = sum(pending_allocations.mapped('amount'))

            # Unassigned = received - assigned - on_hold
            account.unassigned_balance = (
                account.total_received
                - account.total_assigned
                - account.amount_on_hold
            )

    def _compute_counts(self):
        for account in self:
            account.incoming_fund_count = len(account.incoming_fund_ids)
            account.allocation_count = len(account.allocation_ids)

    # ══════════════════════════════════════════════════════════════════
    # DISPLAY NAME
    # ══════════════════════════════════════════════════════════════════

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for account in self:
            if account.code:
                account.display_name = f"[{account.code}] {account.name}"
            else:
                account.display_name = account.name or ''
