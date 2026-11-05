"""Weekly allowance eligibility, independent of optional bonus points."""
from datetime import date, timedelta

REQUIRED_TASKS = ('chambre', 'lit')


def weekly_eligibility(child_id, week_start, completions):
    """Only parent-approved daily records count. Never releases money itself.

    week_start is a Monday (local family calendar date). Records contain child_id,
    task_id, date (ISO calendar date), and status. Missing days remain pending.
    The application must supply trusted, persisted records, not browser claims.
    """
    monday = date.fromisoformat(week_start)
    if monday.weekday() != 0:
        raise ValueError('week_start must be a Monday')
    approved = {
        (record['date'], record['task_id'])
        for record in completions
        if record.get('child_id') == child_id and record.get('status') == 'approved'
    }
    missing = []
    for offset in range(7):
        day = (monday + timedelta(days=offset)).isoformat()
        for task in REQUIRED_TASKS:
            if (day, task) not in approved:
                missing.append({'date': day, 'task_id': task})
    return {
        'eligible': not missing,
        'approved_count': 14 - len(missing),
        'required_count': 14,
        'missing': missing,
    }
