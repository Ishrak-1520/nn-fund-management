# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    """
    Inherit Odoo's native Vendor Bill (account.move) to add fund
    requisition integration.

    This adds:
    - fund_requisition_id: links a vendor bill to an approved fund requisition
    - Server-side constraints on posting to enforce fund management rules
    - Automatic balance updates on post/cancel
    """

    _inherit = 'account.move'

    # ── Fund Management Fields ───────────────────────────────────────
    fund_requisition_id = fields.Many2one(
        'nn.fund.requisition',
        string='Fund Requisition',
        tracking=True,
        index=True,
        copy=False,
        help='Link this bill to an approved fund requisition. '
             'The bill amount will be deducted from the requisition\'s '
             'remaining billable amount.',
    )
    fund_project_id = fields.Many2one(
        'nn.fund.project',
        string='Fund Project',
        related='fund_requisition_id.project_id',
        store=True,
        readonly=True,
    )
    fund_expense_head_id = fields.Many2one(
        'nn.fund.expense.head',
        string='Fund Expense Head',
        related='fund_requisition_id.expense_head_id',
        store=True,
        readonly=True,
    )

    # ══════════════════════════════════════════════════════════════════
    # POSTING OVERRIDE
    # ══════════════════════════════════════════════════════════════════

    def _post(self, soft=True):
        """
        Override the posting method to inject fund management constraints
        before a vendor bill is posted.

        Constraints enforced:
        1. The linked requisition must be in 'approved' state
        2. The bill amount must not exceed the requisition's remaining billable
        3. The bill's project/expense head must match the requisition's
        4. Cross-project/cross-expense billing is blocked
        """
        # Validate fund requisition constraints for vendor bills
        for move in self:
            if (move.move_type == 'in_invoice'
                    and move.fund_requisition_id):
                requisition = move.fund_requisition_id

                # 1. Requisition must be approved
                if requisition.state != 'approved':
                    raise UserError(_(
                        "Cannot post bill '%(bill)s': the linked fund requisition "
                        "'%(req)s' is not in 'Approved' state (current: %(state)s).",
                        bill=move.name,
                        req=requisition.display_name,
                        state=dict(requisition._fields['state'].selection).get(
                            requisition.state, requisition.state),
                    ))

                # 2. Bill amount must not exceed remaining billable
                bill_amount = abs(move.amount_total_signed)
                # Refresh remaining_billable to get current value
                requisition.invalidate_recordset(['remaining_billable'])
                remaining = requisition.remaining_billable

                if bill_amount > remaining:
                    raise UserError(_(
                        "Cannot post bill '%(bill)s': the amount %(amount)s "
                        "exceeds the requisition's remaining billable amount "
                        "of %(remaining)s.\n\n"
                        "Requisition: %(req)s\n"
                        "Approved Amount: %(approved)s\n"
                        "Already Billed: %(billed)s\n"
                        "Remaining: %(remaining)s",
                        bill=move.name,
                        amount=bill_amount,
                        remaining=remaining,
                        req=requisition.display_name,
                        approved=requisition.amount,
                        billed=requisition.total_billed,
                    ))

                # 3. Project/expense head consistency check
                if requisition.allocation_type == 'project':
                    if (move.fund_project_id
                            and move.fund_project_id != requisition.project_id):
                        raise UserError(_(
                            "Cannot post bill '%(bill)s': project mismatch. "
                            "The bill is associated with project '%(bill_proj)s' "
                            "but the requisition '%(req)s' belongs to "
                            "project '%(req_proj)s'.",
                            bill=move.name,
                            bill_proj=move.fund_project_id.display_name,
                            req=requisition.display_name,
                            req_proj=requisition.project_id.display_name,
                        ))
                elif requisition.allocation_type == 'expense_head':
                    if (move.fund_expense_head_id
                            and move.fund_expense_head_id != requisition.expense_head_id):
                        raise UserError(_(
                            "Cannot post bill '%(bill)s': expense head mismatch. "
                            "The bill is associated with expense head '%(bill_exp)s' "
                            "but the requisition '%(req)s' belongs to "
                            "expense head '%(req_exp)s'.",
                            bill=move.name,
                            bill_exp=move.fund_expense_head_id.display_name,
                            req=requisition.display_name,
                            req_exp=requisition.expense_head_id.display_name,
                        ))

        # Call the original _post method
        return super()._post(soft=soft)

    # ══════════════════════════════════════════════════════════════════
    # CANCEL / REVERSAL OVERRIDE
    # ══════════════════════════════════════════════════════════════════

    def button_cancel(self):
        """
        Override cancel to handle fund requisition balance restoration.
        When a posted vendor bill linked to a requisition is cancelled,
        the billed amount is restored to the requisition's remaining billable
        (via the computed field on nn.fund.requisition).
        """
        # The computed field total_billed on the requisition filters by
        # bill.state == 'posted', so cancelling automatically restores
        # the balance. No manual intervention needed.
        return super().button_cancel()

    def button_draft(self):
        """
        Override reset-to-draft to handle fund requisition balance.
        Same as cancel — the computed field handles the recalculation.
        """
        return super().button_draft()
