# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FundIncoming(models.Model):
    """
    Incoming Fund — records money received into a fund account.

    Workflow:
        Draft → Confirmed → (optionally) Cancelled

    On confirmation, the amount is added to the fund account's unassigned balance.
    Duplicate transaction references within the same fund account are blocked.
    """

    _name = 'nn.fund.incoming'
    _description = 'Incoming Fund'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
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
        states={'confirmed': [('readonly', True)]},
    )
    date = fields.Date(
        string='Received Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        states={'confirmed': [('readonly', True)]},
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        tracking=True,
        currency_field='currency_id',
        states={'confirmed': [('readonly', True)]},
    )
    transaction_reference = fields.Char(
        string='Transaction Reference',
        tracking=True,
        states={'confirmed': [('readonly', True)]},
        help='Bank transaction reference number. Must be unique per fund account.',
    )
    sender = fields.Char(
        string='Sender / Source',
        tracking=True,
        states={'confirmed': [('readonly', True)]},
    )
    description = fields.Text(
        string='Description',
        states={'confirmed': [('readonly', True)]},
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'nn_fund_incoming_attachment_rel',
        'incoming_id',
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
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )
    confirmed_by = fields.Many2one(
        'res.users',
        string='Confirmed By',
        readonly=True,
        copy=False,
    )
    confirmed_date = fields.Datetime(
        string='Confirmed Date',
        readonly=True,
        copy=False,
    )

    # ══════════════════════════════════════════════════════════════════
    # CONSTRAINTS
    # ══════════════════════════════════════════════════════════════════

    _sql_constraints = [
        (
            'unique_transaction_ref_per_account',
            'UNIQUE(transaction_reference, fund_account_id)',
            'The transaction reference must be unique within the same fund account.'
        ),
    ]

    @api.constrains('amount')
    def _check_amount_positive(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_(
                    "The incoming fund amount must be greater than zero."
                ))

    # ══════════════════════════════════════════════════════════════════
    # CRUD OVERRIDES
    # ══════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'nn.fund.incoming'
                ) or 'New'
        return super().create(vals_list)

    def unlink(self):
        for record in self:
            if record.state == 'confirmed':
                raise UserError(_(
                    "You cannot delete a confirmed incoming fund record. "
                    "Please cancel it first."
                ))
        return super().unlink()

    # ══════════════════════════════════════════════════════════════════
    # WORKFLOW ACTIONS
    # ══════════════════════════════════════════════════════════════════

    def action_confirm(self):
        """
        Confirm the incoming fund.
        Only Finance Users or Fund Administrators can confirm.
        Adds the amount to the fund account's unassigned balance
        (via the computed field on nn.fund.account).
        """
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Only draft incoming funds can be confirmed."))

            # Server-side permission check
            if not self.env.user.has_group(
                    'nn_fund_management.group_finance_user'):
                raise UserError(_(
                    "Only Finance Users can confirm incoming funds."
                ))

            record.write({
                'state': 'confirmed',
                'confirmed_by': self.env.user.id,
                'confirmed_date': fields.Datetime.now(),
            })

    def action_cancel(self):
        """
        Cancel a confirmed incoming fund.
        Only Fund Administrators can cancel confirmed records.
        The fund account balance will be recomputed automatically.
        """
        for record in self:
            if record.state == 'draft':
                record.write({'state': 'cancelled'})
                continue

            if record.state != 'confirmed':
                raise UserError(_("Only confirmed incoming funds can be cancelled."))

            # Only administrators can cancel confirmed funds
            if not self.env.user.has_group(
                    'nn_fund_management.group_fund_administrator'):
                raise UserError(_(
                    "Only Fund Administrators can cancel confirmed incoming funds."
                ))

            # Check that cancelling won't cause negative unassigned balance
            account = record.fund_account_id
            projected_unassigned = account.unassigned_balance - record.amount
            if projected_unassigned < 0:
                raise UserError(_(
                    "Cannot cancel this incoming fund. "
                    "The fund account '%(account)s' would have a negative "
                    "unassigned balance of %(balance)s. "
                    "Please release allocations first.",
                    account=account.display_name,
                    balance=projected_unassigned,
                ))

            record.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        """Reset a cancelled incoming fund back to draft."""
        for record in self:
            if record.state != 'cancelled':
                raise UserError(_(
                    "Only cancelled incoming funds can be reset to draft."
                ))
            record.write({
                'state': 'draft',
                'confirmed_by': False,
                'confirmed_date': False,
            })
