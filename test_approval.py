#!/usr/bin/env python3
"""
Test script for the approval system implementation
"""

from approval import ApprovalRequest, request_approval, display_time_entries_preview
from entry import TimeEntry

def test_approval_system():
    """Test the approval flow with sample data"""
    
    # Create test time entries
    test_entries = [
        TimeEntry(
            description="Work on approval system implementation",
            start_date="2025-06-08",
            start_time="09:00:00",
            end_date="2025-06-08", 
            end_time="10:30:00",
            duration="01:30:00",
            project="Smart Time Logger",
            task=None,
        ),
        TimeEntry(
            description="Code review and testing",
            start_date="2025-06-08",
            start_time="10:30:00",
            end_date="2025-06-08", 
            end_time="11:00:00",
            duration="00:30:00",
            project="Smart Time Logger",
            task=None,
        ),
        TimeEntry(
            description="Documentation writing",
            start_date="2025-06-08",
            start_time="11:00:00",
            end_date="2025-06-08", 
            end_time="12:00:00",
            duration="01:00:00",
            project="Smart Time Logger",
            task=None,
        )
    ]
    
    print("Testing approval system with sample time entries...")
    print("=" * 60)
    
    # Create approval request
    request = ApprovalRequest(
        tool_name="create_time_entries",
        description=f"Create {len(test_entries)} time entries in Toggl workspace", 
        data=test_entries,
        preview_func=display_time_entries_preview
    )
    
    # Test approval flow
    approved, instructions = request_approval(request)
    
    print(f"\nTest Result:")
    print(f"Approved: {approved}")
    print(f"Instructions: {instructions}")
    
    return approved, instructions

if __name__ == "__main__":
    test_approval_system()
