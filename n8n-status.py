#!/usr/bin/env python3
"""
n8n CLI Workflow Status Script v0.1.0
Andrew Horton

https://github.com/urbanadventurer/n8n_tools

Copyright (c) 2025
License: MIT

This script queries an SQLite database containing n8n workflow
execution records and shows execution statistics in a nicely formatted output.

n8n (https://n8n.io) is a workflow automation platform that allows you to
connect different services and automate tasks.

Requirements:
    - Python 3.6+
    - SQLite3 (included in Python standard library)
    - n8n database file (typically found in ~/.n8n or your custom n8n data directory)

Examples:
    # Show the last 15 workflow executions
    python3 n8n-status.py --db-path /path/to/n8n/database.sqlite --limit 15
    
"""

import argparse
import configparser
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

class Colors:
    RED = '\x1b[31m'
    GREEN = '\x1b[32m'
    YELLOW = '\x1b[33m'
    BLUE = '\x1b[34m'
    MAGENTA = '\x1b[35m'
    CYAN = '\x1b[36m'
    BOLD = '\x1b[1m'
    UNDERLINE = '\x1b[4m'
    END = '\x1b[0m'

# Using custom formatting for tables

class SqliteConnector:
    """Connector for SQLite database."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.validate_db_path()
        
    def validate_db_path(self):
        """Validate that the database path exists."""
        if not os.path.exists(self.db_path):
            raise ValueError(f"Database file not found at {self.db_path}")
            
    def get_connection(self):
        """Create and return a database connection with row factory set."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Failed to connect to database: {e}")
        
    def get_executions(self, limit: Union[int, str] = 100) -> List[Dict]:
        """Get execution data from SQLite with enhanced information
        
        Args:
            limit: Maximum number of executions to return (converted to integer)
            
        Returns:
            List of execution records with enhanced information
        
        Node Name Resolution Process:
            1. Join execution_entity and workflow_entity tables to get basic data
            2. For failed executions, get error details from execution_data
            3. Extract node ID (index) from error information
            4. Use workflow_nodes to map the node index to a human-readable name
            5. Include both node name and ID in the error display
        
        This approach converts cryptic node indices like "5" into meaningful 
        names like "Field Mapping", making error messages much more useful.
        """
        # Parameter validation - convert limit to integer
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 100
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # SQL query to get execution data
                        
            query = """
            SELECT
                e.id,
                CASE WHEN e.finished = 1 THEN 'True' ELSE 'False' END as finished,
                e.status,
                CASE
                    WHEN e.stoppedAt IS NULL AND e.startedAt IS NOT NULL THEN 'Running'
                    WHEN e.status = 'waiting' THEN 'Waiting'
                    WHEN e.status = 'error' THEN 'Error'
                    WHEN e.status = 'success' THEN 'Success'
                    WHEN e.status = 'crashed' THEN 'Crashed'
                    WHEN e.status = 'canceled' THEN 'Canceled'
                    ELSE e.status
                END as display_status,
                CASE
                    WHEN e.stoppedAt IS NOT NULL AND e.startedAt IS NOT NULL
                    THEN CAST((julianday(e.stoppedAt) - julianday(e.startedAt)) * 86400000 AS INTEGER)
                    WHEN e.startedAt IS NOT NULL
                    THEN CAST((julianday('now') - julianday(e.startedAt)) * 86400000 AS INTEGER)
                    ELSE 0
                END as execution_time_ms,
                w.name as workflow_name,
                e.startedAt as started_at,
                e.stoppedAt as stopped_at,
                e.workflowId as workflow_id,
                w.nodes as workflow_nodes,
                COALESCE(e.retryOf, NULL) as retry_of,
                e.mode as execution_mode,
                0 as retries
            FROM
                execution_entity e
            JOIN
                workflow_entity w ON e.workflowId = w.id
            WHERE
                e.startedAt IS NOT NULL
            ORDER BY
                e.startedAt DESC
            LIMIT ?
            """
            
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, (limit,))
            
            # Convert to list of dictionaries
            executions = [dict(row) for row in cursor.fetchall()]
            
            # Enhance each execution with additional information
            for execution in executions:
                display_status = execution['display_status']
                
                # Only add error information for failed executions
                if display_status == 'Error':
                    error_info = self.get_execution_errors(execution['id']) or {}
                    
                    # Set error message - use provided message or default to 'Unknown error'
                    execution['error_message'] = error_info.get('message', 'Unknown error')
                    
                    # Get node ID from error info
                    node_id = error_info.get('node_id')
                    
                    # Try to get the node name from workflow_nodes if available
                    node_name = self._get_node_name_from_workflow(execution.get('workflow_nodes'), node_id)
                    
                    # Always set the node name to something meaningful
                    if node_name:
                        # We found a proper node name from the workflow
                        execution['error_node'] = node_name
                    elif node_id:
                        # Use the node ID as the name if we don't have a proper name
                        execution['error_node'] = f'Node {node_id}'
                    else:
                        # Fallback if we somehow have neither
                        execution['error_node'] = 'Unknown node'
                        
                    # Always store the node ID if available
                    execution['error_node_id'] = node_id
                    
            return executions
            
        except sqlite3.Error as e:
            print(f"Database error in get_executions: {e}")
            return []

            
    
    def get_execution_errors(self, execution_id: str) -> Optional[Dict]:
        """Get detailed error information for failed executions.
        
        Args:
            execution_id: The ID of the execution to get error info for
            
        Returns:
            A dictionary with error details or None if not found
        
        Database Tables and Fields Used:
            - execution_data: Contains detailed execution data
              - executionId: References the execution_entity
              - data: JSON string with detailed execution information
                - Contains error information and node references
        
        Error Information Flow:
            1. Query execution_data table for the specific execution_id
            2. Parse the JSON data to extract error information
            3. Find the 'lastNodeExecuted' field which contains the node index
            4. Store this index in error_info['node_id']
        """
        # Parameter validation
        if not execution_id:
            return None
            
        try:
            # Get database connection
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Query the execution data
                cursor.execute(
                    "SELECT data FROM execution_data WHERE executionId = ? LIMIT 1",
                    (execution_id,)
                )
                result = cursor.fetchone()
                
                if not result or not result['data']:
                    return None
                
                # Parse the execution data
                try:
                    return self._parse_execution_data(json.loads(result['data']))
                except json.JSONDecodeError:
                    return None
                    
        except sqlite3.Error:
            return None
    
    def _parse_execution_data(self, execution_data) -> Dict:
        """Parse execution data to extract basic error information.
        
        Args:
            execution_data: The parsed JSON data from execution_data table
            
        Returns:
            A dictionary with basic error details
        """
        # Default error info structure
        error_info = {
            'message': 'Unknown error',
            'node': 'Unknown',
            'node_id': None
        }
        
        # Handle dictionary structure
        if isinstance(execution_data, dict):
            if 'error' in execution_data:
                error = execution_data['error']
                node_id = execution_data.get('lastNodeExecuted', 'Unknown')
                error_info['node_id'] = node_id
                error_info['node'] = node_id  # Will be replaced with actual name later if available
                
                if isinstance(error, dict):
                    error_info['message'] = error.get('message', 'Unknown error')
                else:
                    error_info['message'] = str(error)
            return error_info
        
        # Handle list structure (newer n8n versions)
        if isinstance(execution_data, list):
            for item in execution_data:
                if isinstance(item, dict):
                    # Extract error message
                    if 'error' in item:
                        error_info['message'] = (item['error'].get('message', 'Unknown error') 
                                               if isinstance(item['error'], dict) 
                                               else str(item['error']))
                    # Extract node ID
                    if 'lastNodeExecuted' in item:
                        node_id = item['lastNodeExecuted']
                        error_info['node_id'] = node_id
                        error_info['node'] = node_id  # Will be replaced with actual name later if available
            
        return error_info
    

        
    def _get_node_name_from_workflow(self, workflow_nodes_json, node_id):
        """Extract node name from workflow nodes JSON data.
        
        Args:
            workflow_nodes_json: JSON string containing workflow nodes data
                This comes from the 'nodes' field in the workflow_entity table.
                It contains an array of node objects, each with 'id', 'name', 'type', etc.
            node_id: The ID of the node to find
                This comes from the 'lastNodeExecuted' field in the execution_data.
                In this n8n setup, it's a numeric index into the nodes array.
            
        Returns:
            The name of the node if found, otherwise None
        
        Database Tables and Fields:
            - workflow_entity: Contains workflow definitions
              - id: Unique identifier for the workflow
              - name: Human-readable name of the workflow
              - nodes: JSON string containing all nodes in the workflow
            
            - execution_entity: Contains basic execution information
              - id: Unique identifier for the execution
              - workflowId: References the workflow that was executed
              - status: Current status of the execution (e.g., 'error', 'success')
            
            - execution_data: Contains detailed execution data
              - executionId: References the execution_entity
              - data: JSON string with detailed execution information
                - Contains 'lastNodeExecuted' field with the node index that failed
        
        JSON Structure Example (nodes field in workflow_entity):
        [{
          "id": "77231080-cb0c-4deb-8e2d-b326a0eb8979",
          "name": "Run daily",
          "type": "n8n-nodes-base.scheduleTrigger",
          "typeVersion": 1,
          "position": [200, 20]
        }, ...]
        """
        if not workflow_nodes_json or not node_id:
            return None
            
        try:
            # Parse the nodes JSON from workflow_entity.nodes field
            nodes = json.loads(workflow_nodes_json)
            
            # In this n8n setup, the node ID in error data is a numeric index
            # The 'lastNodeExecuted' field in execution_data contains this index
            try:
                # Convert node_id to integer index
                index = int(node_id)
                # Check if index is valid for the nodes array
                if 0 <= index < len(nodes):
                    # Return the name of the node at this index
                    return nodes[index].get('name')
            except (ValueError, TypeError):
                # If node_id can't be converted to an integer or other error occurs
                pass
                    
            return None
        except (json.JSONDecodeError, TypeError):
            return None
    

# Utility functions outside of the class
def format_time_ms(ms: Union[int, float, str]) -> str:
    """Format milliseconds into a human-readable format"""
    try:
        # Convert to integer as requested
        ms = int(float(ms))
    except (ValueError, TypeError):
        return "N/A"
    
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    elif ms < 3600000:
        return f"{ms/60000:.1f}m"
    else:
        return f"{ms/3600000:.1f}h"


def print_table(data: List[Dict]) -> None:
    """Print a formatted table of workflow executions with enhanced details.
    
    Args:
        data: A list of dictionaries with execution data
    """
    if not data:
        print("No data available - No execution records found in database")
        return
    
    
    # Define headers and column widths with new order
    headers = [
        "Workflow", "Started At", "Status", "Execution ID"
    ]
    column_widths = [45, 20, 35, 12]
    
    # Truncation helpers
    def truncate(text, width):
        text_str = str(text)
        if len(text_str) > width:
            return text_str[:width-3] + '...'
        return text_str
    
    # Format the header row
    header_row = ""
    for i, header in enumerate(headers):
        header_row += f"{header:{column_widths[i]}}"  # Pad the header to its column width
    print(f"{Colors.BOLD}{header_row}{Colors.END}")
    
    # Print a separator line
    separator = "-" * sum(column_widths)
    print(separator)
    
    # Print each row
    for row in data:
        # Get status with color
        status = row.get('display_status', row.get('status', 'Unknown'))
        
        # Format basic info
        execution_id = truncate(row.get('id', 'Unknown'), column_widths[3])
        workflow_name = row.get('workflow_name', 'Unknown')  # Don't truncate workflow name
        started_at = format_date(row.get('started_at'))
        duration = format_time_ms(row.get('execution_time_ms', 0))
        
        # Apply color based on status and include duration
        if status == 'Running':
            status_str = f"{Colors.BLUE}{status} in {duration}{Colors.END}"
            workflow_display = f"{Colors.BLUE}⟳{Colors.END} {workflow_name}"
        elif status == 'Success':
            status_str = f"{Colors.GREEN}Succeeded in {duration}{Colors.END}"
            workflow_display = f"{Colors.GREEN}✓{Colors.END} {workflow_name}"
        elif status == 'Error':
            status_str = f"{Colors.RED}Error in {duration}{Colors.END}"
            workflow_display = f"{Colors.RED}✕{Colors.END} {workflow_name}"
        elif status == 'Crashed':
            status_str = f"{Colors.RED}Crashed in {duration}{Colors.END}"
            workflow_display = f"{Colors.RED}⛝{Colors.END} {workflow_name}"
        elif status == 'Waiting':
            status_str = f"{Colors.YELLOW}{status} for {duration}{Colors.END}"
            workflow_display = f"{Colors.YELLOW}⏱{Colors.END} {workflow_name}"
        elif status == 'Canceled':
            status_str = f"{Colors.YELLOW}{status} for {duration}{Colors.END}"
            workflow_display = f"{Colors.YELLOW}×{Colors.END} {workflow_name}"
        else:
            status_str = f"{status} in {duration}"
            workflow_display = workflow_name
        
        # Build a string with all fields and proper spacing in new order
        # Workflow name with indicator, Started At, Status with duration, Execution ID
        
        # Calculate visible length of workflow_display (without color codes)
        visible_workflow_length = len(workflow_name) + 2  # +2 for the icon and space
        workflow_padding = max(0, column_widths[0] - visible_workflow_length)
        
        # Build the row text with new order - using fixed positions for consistent alignment
        row_text = workflow_display + " " * workflow_padding
        row_text += f"{started_at:<{column_widths[1]}}"
        
        # Fixed position approach for status and execution ID
        # First add the status with color
        row_text += status_str
        
        # Use a fixed column width for the status column to ensure consistent alignment
        # Add padding after status_str to ensure consistent width regardless of status type
        # Calculate visible length without color codes for proper padding

        # Calculate remaining space for padding
        status_padding = column_widths[2] - len(status_str) + 1
        row_text += " " * status_padding
        
        # Add execution ID with consistent left alignment
        row_text += f"{execution_id}"
        
        print(row_text)
    
        # Print error message for failed executions
        if status == 'Error':
            error_message = row.get('error_message', '')
            error_node = row.get('error_node', 'Unknown')
            
            # Format error display - we should always have a meaningful node name by now
            node_id = row.get('error_node_id')
            
            # If we have a node ID and it's not already part of the name, show it too
            if node_id and not str(node_id) in error_node:
                node_display = f"{error_node} (ID: {node_id})"
            else:
                node_display = error_node
            
            # Truncate very long error messages
            if len(error_message) > 100:
                error_message = error_message[:97] + '...'
            print(f"    {Colors.RED}Error: {error_message} ({node_display}){Colors.END}")
        
        # Print retry information if available
        if row.get('retry_of'):
            retries = row.get('retries', 0)
            print(f"    {Colors.YELLOW}Retry {retries} of execution {row.get('retry_of')}{Colors.END}")
            
        # Print waiting information if available
        

def format_date(date_str: Optional[str]) -> str:
    """Format a date string to a more readable format"""
    if not date_str:
        return "N/A"
    
    try:
        # Try to parse the date using different formats
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            
        return date_str
    except Exception:
        return date_str



def load_config():
    """Load configuration from .n8n-status-config.ini file.
    
    Checks for the file in the current directory and in the user's home directory.
    Returns a dictionary with configuration values.
    """
    config = {
        'db_path': None,
        'limit': 15  # Default limit is now 15
    }
    
    # Check for config file in current directory
    current_dir_config = Path('.n8n-status-config.ini')
    home_dir_config = Path.home() / '.n8n-status-config.ini'
    
    config_path = None
    if current_dir_config.exists():
        config_path = current_dir_config
    elif home_dir_config.exists():
        config_path = home_dir_config
    
    if config_path:
        try:
            parser = configparser.ConfigParser()
            parser.read(config_path)
            
            if 'n8n-status' in parser:
                section = parser['n8n-status']
                
                # Get database path
                if 'db_path' in section:
                    db_path = section['db_path']
                    if db_path:
                        config['db_path'] = os.path.expanduser(db_path)
                
                # Get limit
                if 'limit' in section:
                    try:
                        limit = int(section['limit'])
                        if limit > 0:
                            config['limit'] = limit
                    except ValueError:
                        # If limit is not a valid integer, keep the default
                        pass
        except Exception as e:
            print(f"Warning: Could not load config file {config_path}: {e}")
    
    return config

def main():
    """Main function."""
    # Load configuration
    config = load_config()
    
    parser = argparse.ArgumentParser(description='n8n workflow execution status viewer for SQLite v0.1.0')
    parser.add_argument('--db-path', type=str, 
                      help='Path to SQLite database file')
    parser.add_argument('--limit', type=int, default=config['limit'], 
                      help=f"Maximum number of execution records to display (default: {config['limit']})")

    parser.add_argument('--errors', '-e', action='store_true',
                      help='Show only executions with errors')
    parser.add_argument('--running', '-r', action='store_true',
                      help='Show only running executions')
    parser.add_argument('--waiting', '-w', action='store_true',
                      help='Show only waiting executions')
    parser.add_argument('--id', type=str,
                      help='Show details for a specific execution ID')
    parser.add_argument('--workflow', type=str,
                      help='Filter by workflow name (case insensitive substring match)')
    
    args = parser.parse_args()
    
    # Resolve database path with priority order:
    # 1. Command line argument
    # 2. Environment variable
    # 3. Config file
    # 4. Common locations
    db_path = None
    
    # 1. Command line argument
    if args.db_path:
        db_path = args.db_path
    else:
        # 2. Environment variable
        env_db_path = os.environ.get('N8N_DB_PATH')
        if env_db_path and Path(env_db_path).exists():
            db_path = env_db_path
            print(f"Using database path from environment: {db_path}")
        
        # 3. Config file
        elif config['db_path'] and Path(os.path.expanduser(config['db_path'])).exists():
            db_path = os.path.expanduser(config['db_path'])
            print(f"Using database path from config file: {db_path}")
        
        # 4. Common locations
        else:
            common_paths = [
                Path.home() / '.n8n' / 'database.sqlite',  # Default for desktop app
                Path('database.sqlite'),                   # Current directory
            ]
            
            for path in common_paths:
                if path.exists():
                    db_path = str(path)
                    print(f"Found database at {db_path}")
                    break
    
    # Exit if no database path found or it doesn't exist
    if not db_path or not Path(db_path).exists():
        print(f"Error: SQLite database file not found{' at ' + db_path if db_path else '.'}")
        print("Please specify a valid database path with --db-path.\n")
        parser.print_help()
        sys.exit(1)

    db = SqliteConnector(db_path)

    # Show specific execution details if ID provided
    if args.id:
        # Get the specific execution
        executions = db.get_executions(1000)  # Get a larger set to search through
        execution = next((e for e in executions if e.get('id') == args.id), None)
        
        if execution:
            # Get additional information for error cases
            if execution.get('display_status') == 'Error':
                error_info = db.get_execution_errors(args.id)
                if error_info:
                    execution['error_details'] = error_info
            
            # Display the single execution using print_table
            print_table([execution])
        else:
            print(f"No execution found with ID: {args.id}")
        
        sys.exit(0)

    # Get execution data
    executions = db.get_executions(args.limit)

    # Apply filters if specified
    if args.errors:
        executions = [e for e in executions if e['status'] == 'error']
    if args.running:
        executions = [e for e in executions if e['display_status'] == 'Running']
    if args.waiting:
        executions = [e for e in executions if e['display_status'] == 'Waiting']
    if args.workflow:
        # Case-insensitive workflow name filter
        workflow_filter = args.workflow.lower()
        executions = [e for e in executions if workflow_filter in e['workflow_name'].lower()]

    # Print the table with the filtered executions
    print_table(executions)


if __name__ == "__main__":
    main()
