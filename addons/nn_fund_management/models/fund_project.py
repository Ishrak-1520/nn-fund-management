# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class FundProject(models.Model):
    """
    Fund Project — a project that can receive allocated funds.

    All balance fields are computed automatically and cannot be manually edited.
    Negative balances are structurally impossible when all business rules are
    enforced through the approval workflow.

    Balance formula:
        available_balance = total_allocated + incoming_transfers - outgoing_transfers
                          - requisition_hold - transfer_hold - approved_unspent - total_spent
    """

    _name = 'nn.fund.project'
    _description = 'Fund Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Project Name',
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
        'project_id',
        string='Allocations',
    )
    requisition_ids = fields.One2many(
        'nn.fund.requisition',
        'project_id',
        string='Requisitions',
    )

    # ── Computed balance fields (all store=True, readonly=True) ──────
    total_allocated = fields.Monetary(
        string='Total Allocated',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Sum of all approved allocations to this project.',
    )
    incoming_transfers = fields.Monetary(
        string='Incoming Transfers',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Funds received from other projects or expense heads.',
    )
    outgoing_transfers = fields.Monetary(
        string='Outgoing Transfers',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Funds sent to other projects or expense heads.',
    )
    requisition_hold = fields.Monetary(
        string='Requisition Hold',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Amount reserved by pending requisitions.',
    )
    transfer_hold = fields.Monetary(
        string='Transfer Hold',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Amount reserved by pending outgoing transfers.',
    )
    approved_unspent = fields.Monetary(
        string='Approved (Unspent)',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Approved requisitions not yet fully billed.',
    )
    total_spent = fields.Monetary(
        string='Total Spent',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Total amount billed/spent.',
    )
    available_balance = fields.Monetary(
        string='Available Balance',
        compute='_compute_balances',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Available for new requisitions or transfers.',
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
        for project in self:
            # ── Total allocated (approved allocations) ───────────────
            approved_allocs = project.allocation_ids.filtered(
                lambda a: a.state == 'approved'
            )
            project.total_allocated = sum(approved_allocs.mapped('amount'))

            # ── Incoming transfers (approved, destination = this project) ─
            in_transfers = FundTransfer.search([
                ('dest_type', '=', 'project'),
                ('dest_project_id', '=', project.id),
                ('state', '=', 'approved'),
            ])
            project.incoming_transfers = sum(in_transfers.mapped('amount'))

            # ── Outgoing transfers (approved, source = this project) ──
            out_transfers = FundTransfer.search([
                ('source_type', '=', 'project'),
                ('source_project_id', '=', project.id),
                ('state', '=', 'approved'),
            ])
            project.outgoing_transfers = sum(out_transfers.mapped('amount'))

            # ── Requisition hold (pending requisitions) ──────────────
            pending_reqs = project.requisition_ids.filtered(
                lambda r: r.state in ('submitted', 'gm_approved')
            )
            project.requisition_hold = sum(pending_reqs.mapped('amount'))

            # ── Transfer hold (pending outgoing transfers) ───────────
            pending_out_transfers = FundTransfer.search([
                ('source_type', '=', 'project'),
                ('source_project_id', '=', project.id),
                ('state', 'in', ('submitted', 'gm_approved')),
            ])
            project.transfer_hold = sum(pending_out_transfers.mapped('amount'))

            # ── Approved but unspent (approved reqs minus billed) ────
            approved_reqs = project.requisition_ids.filtered(
                lambda r: r.state in ('approved',)
            )
            project.approved_unspent = sum(
                req.amount - req.total_billed for req in approved_reqs
            )

            # ── Total spent (sum of billed amounts on approved reqs) ─
            project.total_spent = sum(approved_reqs.mapped('total_billed'))

            # ── Available balance ────────────────────────────────────
            project.available_balance = (
                project.total_allocated
                + project.incoming_transfers
                - project.outgoing_transfers
                - project.requisition_hold
                - project.transfer_hold
                - project.approved_unspent
                - project.total_spent
            )

    # ══════════════════════════════════════════════════════════════════
    # DISPLAY NAME
    # ══════════════════════════════════════════════════════════════════

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for project in self:
            if project.code:
                project.display_name = f"[{project.code}] {project.name}"
            else:
                project.display_name = project.name or ''
