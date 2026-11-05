import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from rewards import weekly_eligibility


class WeeklyAllowanceTests(unittest.TestCase):
    def setUp(self):
        self.records = [dict(child_id='alice', task_id=task,
                             date=(date(2026,11,2)+timedelta(days=day)).isoformat(), status='approved')
                        for day in range(7) for task in ('chambre','lit')]

    def test_all_fourteen_approved_unlock(self):
        result = weekly_eligibility('alice','2026-11-02',self.records)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['approved_count'],14)

    def test_bonus_cannot_replace_missing_required_task(self):
        records = self.records[:-1] + [dict(child_id='alice', task_id='linge', date='2026-11-08',status='approved')]*10
        result = weekly_eligibility('alice','2026-11-02',records)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['missing'],[dict(date='2026-11-08',task_id='lit')])

    def test_other_child_other_week_pending_and_duplicates_do_not_count(self):
        records = self.records[:-1]
        records += [dict(self.records[-1],child_id='tiziano'), dict(self.records[-1],date='2026-11-15'),dict(self.records[-1],status='submitted')]
        result = weekly_eligibility('alice','2026-11-02',records + records)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['approved_count'],13)

    def test_new_week_starts_locked(self):
        self.assertFalse(weekly_eligibility('alice','2026-11-09',self.records)['eligible'])

    def test_requires_monday(self):
        with self.assertRaises(ValueError):
            weekly_eligibility('alice','2026-11-03',[])

    def test_catalog_distinguishes_required_and_bonus(self):
        config=json.loads((Path(__file__).resolve().parents[1]/'config/tasks.json').read_text())
        required=[t for t in config['tasks'] if t['category']=='required']
        self.assertEqual({t['id'] for t in required},{'chambre','lit'})
        self.assertTrue(all(t['frequency']=='daily' and t['points']==0 for t in required))
        self.assertEqual(config['allowance']['currency'], 'CHF')
        self.assertEqual(config['allowance']['base_amount_minor_by_child'],
                         {'alice': 500, 'anaelle': 500, 'tiziano': 2500})
