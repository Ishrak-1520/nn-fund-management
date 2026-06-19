# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ApprovalMixin(models.AbstractModel):
    """
    Reusable approval workflow mixin for fund management requests.

    Provides a standardized multi-level approval workflow:
        Draft → Submitted → GM Approval → MD Approval → Approved / Rejected / Cancelled

    Models that inherit this mixin must implement the following hook methods:
        - _on_submit_validate(): Validate business rules before submission
        - _on_submit_hold(): Place funds on hold after submission
        - _on_approval_complete(): Execute post-approval logic
        - _on_rejection(): Release held funds on rejection
        - _on_cancellation(): Release held funds on cancellation

    Usage:
        class MyModel(models.Model):
            _name = 'my.model'
            _inherit = ['nn.approval.mixin', 'mail.thread', 'mail.activity.mixin']
    """

    _name = 'nn.approval.mixin'
    _description = 'Approval Workflow Mixin'

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('gm_approved', 'GM Approved'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )

    # ── Submission info ──────────────────────────────────────────────
    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        readonly=True,
        states={'draft': [('readonly', False)]},
        tracking=True,
        index=True,
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        readonly=True,
        states={'draft': [('readonly', False)]},
        tracking=True,
    )
    submitted_date = fields.Datetime(
        string='Submitted Date',
        readonly=True,
        copy=False,
    )

    # ── GM Approval info ─────────────────────────────────────────────
    gm_approver_id = fields.Many2one(
        'res.users',
        string='GM Approved By',
        readonly=True,
        copy=False,
        tracking=True,
    )
    gm_approval_date = fields.Datetime(
        string='GM Approval Date',
        readonly=True,
        copy=False,
    )
    gm_comment = fields.Text(
        string='GM Comment',
        copy=False,
    )

    # ── MD Approval info ─────────────────────────────────────────────
    md_approver_id = fields.Many2one(
        'res.users',
        string='MD Approved By',
        readonly=True,
        copy=False,
        tracking=True,
    )
    md_approval_date = fields.Datetime(
        string='MD Approval Date',
        readonly=True,
        copy=False,
    )
    md_comment = fields.Text(
        string='MD Comment',
        copy=False,
    )

    # ── Rejection / Cancellation info ─────────────────────────────────
    rejection_reason = fields.Text(
        string='Rejection Reason',
        copy=False,
    )
    cancelled_by = fields.Many2one(
        'res.users',
        string='Cancelled By',
        readonly=True,
        copy=False,
    )
    cancelled_date = fields.Datetime(
        string='Cancelled Date',
        readonly=True,
        copy=False,
    )

    # ── Approval history ─────────────────────────────────────────────
    approval_history_ids = fields.One2many(
        'nn.approval.history',
        'res_id',
        string='Approval History',
        domain=lambda self: [('res_model', '=', self._name)],
        readonly=True,
    )

    # ══════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ══════════════════════════════════════════════════════════════════

    def _check_user_is_gm_approver(self):
        """Check that the current user belongs to the GM Approver group."""
        if not self.env.user.has_group('nn_fund_management.group_gm_approver'):
            raise UserError(_(
                "You do not have permission to approve at the GM level. "
                "Only users in the 'GM Approver' group can perform this action."
            ))

    def _check_user_is_md_approver(self):
        """Check that the current user belongs to the MD Approver group."""
        if not self.env.user.has_group('nn_fund_management.group_md_approver'):
            raise UserError(_(
                "You do not have permission to approve at the MD level. "
                "Only users in the 'MD Approver' group can perform this action."
            ))

    def _check_not_self_approval(self):
        """
        Prevent users from approving their own requests,
        unless they are a Fund Administrator.
        """
        for record in self:
            if (record.requested_by == self.env.user
                    and not self.env.user.has_group(
                        'nn_fund_management.group_fund_administrator')):
                raise UserError(_(
                    "You cannot approve your own request. "
                    "Please ask another authorized approver."
                ))

    def _lock_balance_record(self, record):
        """
        Acquire a PostgreSQL FOR UPDATE row-level lock on the given record
        to prevent concurrent modifications during balance validation.

        This is the key mechanism for preventing double-spending in concurrent
        scenarios. The lock is held until the current transaction commits
        or rolls back.

        Args:
            record: The record to lock (e.g., fund account, project, expense head)
        """
        # Table name comes from Odoo model definition (_table), not user input
        # so this is safe from SQL injection
        query = "SELECT id FROM %s WHERE id = %%s FOR UPDATE" % record._table
        self.env.cr.execute(query, [record.id])

    def _create_approval_history(self, action, comment=None, **extra_vals):
        """
        Create an approval history entry for the current action.

        Args:
            action: The action being performed (e.g., 'submit', 'gm_approve')
            comment: Optional comment from the approver
            **extra_vals: Additional field values for the history record
        """
        self.ensure_one()
        vals = {
            'res_model': self._name,
            'res_id': self.id,
            'action': action,
            'user_id': self.env.user.id,
            'date': fields.Datetime.now(),
            'previous_state': self.state,
            'comment': comment,
        }
        vals.update(extra_vals)
        return self.env['nn.approval.history'].sudo().create(vals)

    # ══════════════════════════════════════════════════════════════════
    # HOOK METHODS (to be overridden by inheriting models)
    # ══════════════════════════════════════════════════════════════════

    def _on_submit_validate(self):
        """
        Validate business rules before submission.
        Should raise UserError/ValidationError if validation fails.
        Must be overridden by inheriting models.
        """
        pass

    def _on_submit_hold(self):
        """
        Place funds on hold after successful validation.
        Called after _on_submit_validate() passes.
        Must be overridden by inheriting models.
        """
        pass

    def _on_approval_complete(self):
        """
        Execute business logic after final approval (MD approval).
        For example, move funds from hold to the destination.
        Must be overridden by inheriting models.
        """
        pass

    def _on_rejection(self):
        """
        Release held funds when the request is rejected.
        Must be overridden by inheriting models.
        """
        pass

    def _on_cancellation(self):
        """
        Release held funds when the request is cancelled.
        Must be overridden by inheriting models.
        """
        pass

    def _get_approval_amount(self):
        """
        Return the monetary amount associated with this request.
        Used for audit history recording.
        Override in inheriting models.
        """
        self.ensure_one()
        return getattr(self, 'amount', 0.0)

    def _get_fund_account(self):
        """
        Return the related fund account for audit history, if applicable.
        Override in inheriting models.
        """
        self.ensure_one()
        return getattr(self, 'fund_account_id', False)

    def _get_project(self):
        """
        Return the related project for audit history, if applicable.
        Override in inheriting models.
        """
        self.ensure_one()
        return getattr(self, 'project_id', False)

    def _get_expense_head(self):
        """
        Return the related expense head for audit history, if applicable.
        Override in inheriting models.
        """
        self.ensure_one()
        return getattr(self, 'expense_head_id', False)

    # ══════════════════════════════════════════════════════════════════
    # WORKFLOW ACTIONS
    # ══════════════════════════════════════════════════════════════════

    def action_submit(self):
        """Submit the request for approval. Validates and places funds on hold."""
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Only draft requests can be submitted."))

            # Run business validation (may acquire FOR UPDATE locks)
            record._on_submit_validate()

            # Place funds on hold
            record._on_submit_hold()

            # Record history before state change
            record._create_approval_history(
                action='submit',
                new_state='submitted',
                amount=record._get_approval_amount(),
                fund_account_id=record._get_fund_account() and record._get_fund_account().id,
                project_id=record._get_project() and record._get_project().id,
                expense_head_id=record._get_expense_head() and record._get_expense_head().id,
                reference=record.display_name,
            )

            # Update state
            record.write({
                'state': 'submitted',
                'submitted_date': fields.Datetime.now(),
            })

    def action_gm_approve(self):
        """GM approves the request."""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_(
                    "Only submitted requests can be approved by GM. "
                    "Current status: %s", dict(record._fields['state'].selection).get(record.state)
                ))

            record._check_user_is_gm_approver()
            record._check_not_self_approval()

            record._create_approval_history(
                action='gm_approve',
                comment=record.gm_comment,
                new_state='gm_approved',
                amount=record._get_approval_amount(),
                fund_account_id=record._get_fund_account() and record._get_fund_account().id,
                project_id=record._get_project() and record._get_project().id,
                expense_head_id=record._get_expense_head() and record._get_expense_head().id,
                reference=record.display_name,
            )

            record.write({
                'state': 'gm_approved',
                'gm_approver_id': self.env.user.id,
                'gm_approval_date': fields.Datetime.now(),
            })

    def action_md_approve(self):
        """MD approves the request. This is the final approval step."""
        for record in self:
            if record.state != 'gm_approved':
                raise UserError(_(
                    "Only GM-approved requests can be approved by MD. "
                    "The GM must approve before the MD."
                ))

            record._check_user_is_md_approver()
            record._check_not_self_approval()

            # Execute post-approval business logic BEFORE state change
            # This ensures any errors roll back cleanly
            record._on_approval_complete()

            record._create_approval_history(
                action='md_approve',
                comment=record.md_comment,
                new_state='approved',
                amount=record._get_approval_amount(),
                fund_account_id=record._get_fund_account() and record._get_fund_account().id,
                project_id=record._get_project() and record._get_project().id,
                expense_head_id=record._get_expense_head() and record._get_expense_head().id,
                reference=record.display_name,
            )

            record.write({
                'state': 'approved',
                'md_approver_id': self.env.user.id,
                'md_approval_date': fields.Datetime.now(),
            })

    def action_gm_reject(self):
        """GM rejects the request. Releases held funds."""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_("Only submitted requests can be rejected by GM."))

            record._check_user_is_gm_approver()

            # Release held funds
            record._on_rejection()

            record._create_approval_history(
                action='gm_reject',
                comment=record.rejection_reason,
                new_state='rejected',
                amount=record._get_approval_amount(),
                fund_account_id=record._get_fund_account() and record._get_fund_account().id,
                project_id=record._get_project() and record._get_project().id,
                expense_head_id=record._get_expense_head() and record._get_expense_head().id,
                reference=record.display_name,
            )

            record.write({
                'state': 'rejected',
            })

    def action_md_reject(self):
        """MD rejects the request after GM approval. Releases held funds."""
        for record in self:
            if record.state != 'gm_approved':
                raise UserError(_(
                    "Only GM-approved requests can be rejected by MD."
                ))

            record._check_user_is_md_approver()

            # Release held funds
            record._on_rejection()

            record._create_approval_history(
                action='md_reject',
                comment=record.rejection_reason,
                new_state='rejected',
                amount=record._get_approval_amount(),
                fund_account_id=record._get_fund_account() and record._get_fund_account().id,
                project_id=record._get_project() and record._get_project().id,
                expense_head_id=record._get_expense_head() and record._get_expense_head().id,
                reference=record.display_name,
            )

            record.write({
                'state': 'rejected',
            })

    def action_cancel(self):
        """
        Cancel the request. Can be done from submitted or approved states.
        Only Fund Administrators can cancel approved requests.
        Releases any held or assigned funds.
        """
        for record in self:
            if record.state == 'draft':
                # Draft can be cancelled without fund release
                record.write({
                    'state': 'cancelled',
                    'cancelled_by': self.env.user.id,
                    'cancelled_date': fields.Datetime.now(),
                })
                continue

            if record.state in ('rejected', 'cancelled'):
                raise UserError(_("This request is already rejected or cancelled."))

            # Only administrators can cancel approved requests
            if record.state == 'approved':
                if not self.env.user.has_group(
                        'nn_fund_management.group_fund_administrator'):
                    raise UserError(_(
                        "Only Fund Administrators can cancel approved requests."
                    ))

            # Release held/assigned funds
            record._on_cancellation()

            record._create_approval_history(
                action='cancel',
                comment=record.rejection_reason,
                new_state='cancelled',
                amount=record._get_approval_amount(),
                fund_account_id=record._get_fund_account() and record._get_fund_account().id,
                project_id=record._get_project() and record._get_project().id,
                expense_head_id=record._get_expense_head() and record._get_expense_head().id,
                reference=record.display_name,
            )

            record.write({
                'state': 'cancelled',
                'cancelled_by': self.env.user.id,
                'cancelled_date': fields.Datetime.now(),
            })

    def action_reset_to_draft(self):
        """
        Reset a rejected or cancelled request back to draft.
        This does NOT restore any funds — it simply allows re-editing.
        """
        for record in self:
            if record.state not in ('rejected', 'cancelled'):
                raise UserError(_(
                    "Only rejected or cancelled requests can be reset to draft."
                ))

            record._create_approval_history(
                action='reset_draft',
                new_state='draft',
                amount=record._get_approval_amount(),
                reference=record.display_name,
            )

            record.write({
                'state': 'draft',
                'submitted_date': False,
                'gm_approver_id': False,
                'gm_approval_date': False,
                'gm_comment': False,
                'md_approver_id': False,
                'md_approval_date': False,
                'md_comment': False,
                'rejection_reason': False,
                'cancelled_by': False,
                'cancelled_date': False,
            })

    # ══════════════════════════════════════════════════════════════════
    # RECORD PROTECTION
    # ══════════════════════════════════════════════════════════════════

    def unlink(self):
        """Prevent deletion of non-draft records."""
        for record in self:
            if record.state != 'draft':
                raise UserError(_(
                    "You cannot delete a record that is not in draft state. "
                    "Please cancel it first, then reset to draft if you wish to delete."
                ))
        return super().unlink()
