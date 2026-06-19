# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FundDashboard(models.TransientModel):
    _name = 'nn.fund.dashboard'
    _description = 'Fund Management Dashboard'

    company_id = fields.Many2one(
        'res.company', 
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency', 
        related='company_id.currency_id'
    )

    # Fund Account Metrics
    total_received = fields.Monetary(currency_field='currency_id', string='Total Funds Received')
    total_unassigned = fields.Monetary(currency_field='currency_id', string='Unassigned Balance')
    total_held = fields.Monetary(currency_field='currency_id', string='Held Amount')
    total_assigned = fields.Monetary(currency_field='currency_id', string='Assigned Amount')
    
    # Project & Expense Metrics
    total_spent = fields.Monetary(currency_field='currency_id', string='Spent Amount')

    # Pending Counts
    pending_allocations = fields.Integer(string='Pending Allocations')
    pending_requisitions = fields.Integer(string='Pending Requisitions')
    pending_transfers = fields.Integer(string='Pending Transfers')

    # Lists for embedded views
    project_ids = fields.Many2many(
        'nn.fund.project', 
        string='Projects'
    )
    expense_head_ids = fields.Many2many(
        'nn.fund.expense.head', 
        string='Expense Heads'
    )
    recent_movement_ids = fields.Many2many(
        'nn.approval.history', 
        string='Recent Fund Movements'
    )

    @api.model
    def action_open_dashboard(self):
        """
        Calculates real-time metrics across all fund accounts, projects, and expense heads.
        Creates a TransientModel record to act as a dashboard container and returns an action
        to display it as a form view.
        """
        # Fetch records
        accounts = self.env['nn.fund.account'].search([])
        projects = self.env['nn.fund.project'].search([])
        expense_heads = self.env['nn.fund.expense.head'].search([])
        
        # Calculate Pending Approvals
        pending_states = ['submitted', 'gm_approved']
        alloc_count = self.env['nn.fund.allocation'].search_count([('state', 'in', pending_states)])
        req_count = self.env['nn.fund.requisition'].search_count([('state', 'in', pending_states)])
        trans_count = self.env['nn.fund.transfer'].search_count([('state', 'in', pending_states)])

        # Recent Movements (Approval History acts as our audit trail/movement log)
        recent_movements = self.env['nn.approval.history'].search([], order='create_date desc', limit=10)

        # Create the dashboard record
        dashboard = self.create({
            'total_received': sum(accounts.mapped('total_received')),
            'total_unassigned': sum(accounts.mapped('unassigned_balance')),
            'total_held': sum(accounts.mapped('amount_on_hold')),
            'total_assigned': sum(accounts.mapped('total_assigned')),
            'total_spent': sum(projects.mapped('total_spent')) + sum(expense_heads.mapped('total_spent')),
            
            'pending_allocations': alloc_count,
            'pending_requisitions': req_count,
            'pending_transfers': trans_count,
            
            'project_ids': [(6, 0, projects.ids)],
            'expense_head_ids': [(6, 0, expense_heads.ids)],
            'recent_movement_ids': [(6, 0, recent_movements.ids)],
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fund Management Dashboard',
            'res_model': 'nn.fund.dashboard',
            'res_id': dashboard.id,
            'view_mode': 'form',
            'target': 'inline',
        }
