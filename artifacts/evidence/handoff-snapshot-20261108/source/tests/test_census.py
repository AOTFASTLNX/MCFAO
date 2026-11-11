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

    def test_complete_census_and_truncated_trailing_line(self):
        d=summarize('CLASS\t[B\t3\t16000\t15000\nITERATION_STATUS\t0\t0\nCENSUS_END\nALLOC\tbroken')
        self.assertTrue(d['censusCompleted']);self.assertEqual(d['objectsCounted'],3)
        self.assertEqual(d['allocationSamples'],0)

    def test_duplicate_samples_and_negative_sizes_are_rejected(self):
        with self.assertRaises(ValueError):summarize('ALLOC\t1\t5\t[B\t0\nALLOC\t1\t6\t[B\t0\n')
        with self.assertRaises(ValueError):summarize('CLASS\t[B\t1\t-1\t2\n')


if __name__=='__main__':unittest.main()
