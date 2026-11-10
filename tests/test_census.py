import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from summarize_census import summarize


class CensusTests(unittest.TestCase):
    def test_partial_sample_does_not_become_complete_census(self):
        d=summarize('ALLOC\t1\t32\tLjava/util/HashMap$Node;\t0\n'
            'ALLOC_FRAME\t1\tLcom/oracle/graal/pointsto/flow/Builder;\tclone\t2\n'
            'CLASS\t[B\t100\t9000\t8000\nITERATION_STATUS\t0\t0\n')
        self.assertFalse(d['censusCompleted']);self.assertEqual(d['allocationSamples'],1)
        self.assertEqual(d['shallowBytesCounted'],9000)
        self.assertEqual(d['firstPointsToFramePerSample'][0][1],1)

    def test_iteration_error_and_unknown_classes_are_visible(self):
        d=summarize('CLASS\t<unknown>\t2\t64\t0\nITERATION_STATUS\t1\t0\nCENSUS_END\n')
        self.assertFalse(d['censusCompleted']);self.assertEqual(d['unknownClassObjects'],2)

    def test_largest_arrays_are_ranked_and_validated(self):
        d=summarize('SNAPSHOT_BEGIN\tT1\t100\nSNAPSHOT_LARGE\tT1\t[Ljava/util/HashMap$Node;\t2048\n'
            'SNAPSHOT_LARGE\tT1\t[Ljava/util/HashMap$Node;\t65536\nSNAPSHOT_END\tT1\n')
        self.assertEqual([a['elements'] for a in d['scheduledSnapshots'][0]['largestArrays']],[65536,2048])
        with self.assertRaises(ValueError):summarize('SNAPSHOT_LARGE\tT9\t[B\t16\n')
        with self.assertRaises(ValueError):summarize('SNAPSHOT_BEGIN\tT1\t100\nSNAPSHOT_LARGE\tT1\t[B\t-4\n')

    def test_complete_census_and_truncated_trailing_line(self):
        d=summarize('CLASS\t[B\t3\t16000\t15000\nITERATION_STATUS\t0\t0\nCENSUS_END\nALLOC\tbroken')
        self.assertTrue(d['censusCompleted']);self.assertEqual(d['objectsCounted'],3)
        self.assertEqual(d['allocationSamples'],0)

    def test_duplicate_samples_and_negative_sizes_are_rejected(self):
        with self.assertRaises(ValueError):summarize('ALLOC\t1\t5\t[B\t0\nALLOC\t1\t6\t[B\t0\n')
        with self.assertRaises(ValueError):summarize('CLASS\t[B\t1\t-1\t2\n')

    def test_scheduled_snapshots_stay_separate_from_the_oom_census(self):
        d=summarize('SNAPSHOT_BEGIN\tT10\t1000\nSNAPSHOT_STATUS\tT10\t0\t0\t120\n'
            'SNAPSHOT_CLASS\tT10\t[B\t5\t4096\t4000\nSNAPSHOT_CLASS\tT10\tLjava/lang/String;\t2\t48\t0\n'
            'SNAPSHOT_END\tT10\n'
            'SNAPSHOT_BEGIN\tT20\t2000\nSNAPSHOT_STATUS\tT20\t0\t0\t130\n'
            'SNAPSHOT_CLASS\tT20\t[B\t9\t8192\t8000\nSNAPSHOT_END\tT20\n')
        self.assertEqual([s['label'] for s in d['scheduledSnapshots']],['T10','T20'])
        first=d['scheduledSnapshots'][0]
        self.assertTrue(first['completed']);self.assertEqual(first['status'],[0,0,120])
        self.assertEqual(first['objectsCounted'],7);self.assertEqual(first['shallowBytesCounted'],4144)
        self.assertEqual(first['largestShallowClasses'][0]['class'],'[B')
        self.assertEqual([s['shallowBytesCounted'] for s in d['scheduledSnapshots']],[4144,8192])
        # The OOM census aggregates stay empty: snapshots must not be folded into them.
        self.assertEqual(d['shallowBytesCounted'],0);self.assertFalse(d['censusCompleted'])

    def test_incomplete_schedule_is_visible(self):
        d=summarize('SNAPSHOT_BEGIN\tT10\t1000\nSNAPSHOT_CLASS\tT10\t[B\t1\t16\t8\n')
        self.assertFalse(d['scheduledSnapshots'][0]['completed'])
        self.assertIsNone(d['scheduledSnapshots'][0]['status'])
        with self.assertRaises(ValueError):summarize('SNAPSHOT_CLASS\tT99\t[B\t1\t16\t8\n')
        with self.assertRaises(ValueError):summarize('SNAPSHOT_BEGIN\tT1\t1\nSNAPSHOT_BEGIN\tT1\t2\n')


if __name__=='__main__':unittest.main()
