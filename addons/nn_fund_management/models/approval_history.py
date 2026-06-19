# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ApprovalHistory(models.Model):
    """
    Audit trail for all approval workflow actions.

    Records every state transition across fund allocations, requisitions,
    and transfers — capturing who did what, when, and why.

    This model is write-once: records cannot be edited or deleted
    through the UI (only created programmatically by the approval mixin).
    """

    _name = 'nn.approval.history'
    _description = 'Approval History'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    # ── Reference fields ─────────────────────────────────────────────
    res_model = fields.Char(
        string='Related Model',
        required=True,
        readonly=True,
        index=True,
    )
    res_id = fields.Many2oneReference(
        string='Related Record ID',
        model_field='res_model',
        required=True,
        readonly=True,
        index=True,
    )

    # ── Action details ───────────────────────────────────────────────
    action = fields.Selection(
        selection=[
            ('submit', 'Submitted'),
            ('gm_approve', 'GM Approved'),
            ('gm_reject', 'GM Rejected'),
            ('md_approve', 'MD Approved'),
            ('md_reject', 'MD Rejected'),
            ('cancel', 'Cancelled'),
            ('reset_draft', 'Reset to Draft'),
            ('close', 'Closed'),
        ],
        string='Action',
        required=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Performed By',
        required=True,
        readonly=True,
        index=True,
    )
    date = fields.Datetime(
        string='Date & Time',
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )

    # ── State tracking ───────────────────────────────────────────────
    previous_state = fields.Char(
        string='Previous Status',
        readonly=True,
    )
    new_state = fields.Char(
        string='New Status',
        readonly=True,
    )

    # ── Details ──────────────────────────────────────────────────────
    comment = fields.Text(
        string='Comment',
        readonly=True,
    )
    amount = fields.Monetary(
        string='Amount',
        readonly=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )

    # ── Related records ──────────────────────────────────────────────
    fund_account_id = fields.Many2one(
        'nn.fund.account',
        string='Fund Account',
        readonly=True,
        index=True,
    )
    project_id = fields.Many2one(
        'nn.fund.project',
        string='Project',
        readonly=True,
        index=True,
    )
    expense_head_id = fields.Many2one(
        'nn.fund.expense.head',
        string='Expense Head',
        readonly=True,
        index=True,
    )
    reference = fields.Char(
        string='Reference Document',
        readonly=True,
    )

    # ── Computed display name ────────────────────────────────────────
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        readonly=True,
    )

    @api.depends('action', 'user_id', 'date', 'reference')
    def _compute_display_name(self):
        action_labels = dict(self._fields['action'].selection)
        for record in self:
            action_label = action_labels.get(record.action, record.action or '')
            user_name = record.user_id.name or ''
            ref = record.reference or ''
            record.display_name = f"{ref} - {action_label} by {user_name}"
