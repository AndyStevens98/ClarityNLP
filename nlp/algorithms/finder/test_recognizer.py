#!/usr/bin/python3
"""
    Test program for the recognizer modules.
"""

import re
import os
import sys
import json
import argparse
from collections import namedtuple

try:
    import lab_value_recognizer as lvr
except:
    from algorithms.finder import lab_value_recognizer as lvr
    
_VERSION_MAJOR = 0
_VERSION_MINOR = 1
_MODULE_NAME = 'test_recognizer.py'

_RESULT_FIELDS = ['match_text']
_Result = namedtuple('_Result', _RESULT_FIELDS)
_Result.__new__.__defaults__ = (None,) * len(_Result._fields)


###############################################################################
def _compare_results(
        computed_values,
        expected_values,
        sentence,
        field_list):

    # check that len(computed) == len(expected)
    if len(computed_values) != len(expected_values):
        print('\tMismatch in computed vs. expected results: ')
        print('\tSentence: {0}'.format(sentence))
        print('\tComputed: ')
        for v in computed_values:
            print('\t\t{0}'.format(v))
        print('\tExpected: ')
        for v in expected_values:
            print('\t\t{0}'.format(v))

        print('NAMEDTUPLE: ')
        for k,v in v._asdict().items():
            print('\t{0} => {1}'.format(k,v))

        return False

    # check fields for each result
    failures = []
    for i, t in enumerate(computed_values):
        # iterate over fields of current result
        for field, value in t._asdict().items():
            # remove trailing whitespace, if any, from computed value
            if str == type(value):
                value = value.strip()
            expected = expected_values[i]._asdict()
            # compare only those fields in _RESULT_FIELDS
            if field in field_list:
                if value != expected[field]:
                    # append as namedtuples
                    failures.append( (t, expected_values[i]) )

    if len(failures) > 0:
        print(sentence)
        for f in failures:
            # extract fields with values not equal to None
            c = [ (k,v) for k,v in f[0]._asdict().items()
                  if v is not None and k in field_list]
            e = [ (k,v) for k,v in f[1]._asdict().items() if v is not None]
            print('\tComputed: {0}'.format(c))
            print('\tExpected: {0}'.format(e))
            
        return False

    return True
    

###############################################################################
def _run_tests(test_data):

    for sentence, expected_values in test_data.items():

        # computed values are finder_overlap.Candidate namedtuples
        # relevant field is 'match_text'
        computed_values = lvr.run(sentence)
        
        ok = _compare_results(
            computed_values,
            expected_values,
            sentence,
            _RESULT_FIELDS)

        if not ok:
            return False
        
    return True


###############################################################################
def test_lab_value_recognizer():

    test_data = {
        'VS: T 95.6 HR 45 BP 75/30 RR 17 98% RA.':[
            _Result(match_text='T 95.6'),
            _Result(match_text='HR 45'),
            _Result(match_text='BP 75/30'),
            _Result(match_text='RR 17'),
            _Result(match_text='98% RA')
        ],
        'VS T97.3 P84 BP120/56 RR16 O2Sat98 2LNC':[
            _Result(match_text='T97.3'),
            _Result(match_text='P84'),
            _Result(match_text='BP120/56'),
            _Result(match_text='RR16'),
            _Result(match_text='O2Sat98 2LNC')
        ],
        'Height: (in) 74 Weight (lb): 199 BSA (m2): 2.17 m2 ' +\
        'BP (mm Hg): 140/91 HR (bpm): 53':[
            _Result(match_text='Height: (in) 74'),
            _Result(match_text='Weight (lb): 199'),
            _Result(match_text='BSA (m2): 2.17 m2'),
            _Result(match_text='BP (mm Hg): 140/91'),
            _Result(match_text='HR (bpm): 53')
        ],
        'Vitals: T: 99 BP: 115/68 P: 79 R:21 O2: 97':[
            _Result(match_text='T: 99'),
            _Result(match_text='BP: 115/68'),
            _Result(match_text='P: 79'),
            _Result(match_text='R:21'),
            _Result(match_text='O2: 97')
        ],
        'Vitals - T 95.5 BP 132/65 HR 78 RR 20 SpO2 98%/3L':[
            _Result(match_text='T 95.5'),
            _Result(match_text='BP 132/65'),
            _Result(match_text='HR 78'),
            _Result(match_text='RR 20'),
            _Result(match_text='SpO2 98%/3L')
        ],
        'VS: T=98 BP= 122/58  HR= 7 RR= 20  O2 sat= 100% 2L NC':[
            _Result(match_text='T=98'),
            _Result(match_text='BP= 122/58'),
            _Result(match_text='HR= 7'),
            _Result(match_text='RR= 20'),
            _Result(match_text='O2 sat= 100% 2L NC')
        ],
        'VS:  T-100.6, HR-105, BP-93/46, RR-16, Sats-98% 3L/NC':[
            _Result(match_text='T-100.6'),
            _Result(match_text='HR-105'),
            _Result(match_text='BP-93/46'),
            _Result(match_text='RR-16'),
            _Result(match_text='Sats-98% 3L/NC')
        ],
        'VS - Temp. 98.5F, BP115/65 , HR103 , R16 , 96O2-sat % RA':[
            _Result(match_text='Temp. 98.5F'),
            _Result(match_text='BP115/65'),
            _Result(match_text='HR103'),
            _Result(match_text='R16'),
            _Result(match_text='96O2-sat % RA')
        ],
        'Vitals: Temp 100.2 HR 72 BP 184/56 RR 16 sats 96% on RA':[
            _Result(match_text='Temp 100.2'),
            _Result(match_text='HR 72'),
            _Result(match_text='BP 184/56'),
            _Result(match_text='RR 16'),
            _Result(match_text='sats 96% on RA')
        ],
        'PHYSICAL EXAM: O: T: 98.8 BP: 123/60   HR:97    R 16  O2Sats100%':[
            _Result(match_text='T: 98.8'),
            _Result(match_text='BP: 123/60'),
            _Result(match_text='HR:97'),
            _Result(match_text='R 16'),
            _Result(match_text='O2Sats100%')
        ],
        'VS before transfer were 85 BP 99/34 RR 20 SpO2% 99/bipap 10/5 50%.':[
            _Result(match_text='BP 99/34'),
            _Result(match_text='RR 20'),
            _Result(match_text='SpO2% 99/bipap')
        ],
        'Initial vs were: T 98 P 91 BP 122/63 R 20 O2 sat 95%RA.':[
            _Result(match_text='T 98'),
            _Result(match_text='P 91'),
            _Result(match_text='BP 122/63'),
            _Result(match_text='R 20'),
            _Result(match_text='O2 sat 95%RA')
        ],
        'Initial vitals were HR 106 BP 88/56 RR 20 O2 Sat 85% 3L.':[
            _Result(match_text='HR 106'),
            _Result(match_text='BP 88/56'),
            _Result(match_text='RR 20'),
            _Result(match_text='O2 Sat 85% 3L')
        ],
        'Initial vs were: T=99.3 P=120 BP=111/57 RR=24 POx=100%.':[
            _Result(match_text='T=99.3'),
            _Result(match_text='P=120'),
            _Result(match_text='BP=111/57'),
            _Result(match_text='RR=24'),
            _Result(match_text='POx=100%')
        ],
        'At transfer vitals were HR=120 BP=109/44 RR=29 POx=93% on 8L FM.':[
            _Result(match_text='HR=120'),
            _Result(match_text='BP=109/44'),
            _Result(match_text='RR=29'),
            _Result(match_text='POx=93% on 8L FM')
        ],
        "Vitals as follows: BP 120/80 HR 60-80's RR  SaO2 96% 6L NC.":[
            _Result(match_text='BP 120/80'),
            _Result(match_text="HR 60-80's"),
            _Result(match_text='SaO2 96% 6L NC')
        ],
        'Vital signs were T 97.5 HR 62 BP 168/60 RR 18 95% RA.':[
            _Result(match_text='T 97.5'),
            _Result(match_text='HR 62'),
            _Result(match_text='BP 168/60'),
            _Result(match_text='RR 18'),
            _Result(match_text='95% RA')
        ],
        'T 99.4 P 160 R 56 BP 60/36 mean 44 O2 sat 97% Wt 3025 grams ' +\
        'Lt 18.5 inches HC 35 cm':[
            _Result(match_text='T 99.4'),
            _Result(match_text='P 160'),
            _Result(match_text='R 56'),
            _Result(match_text='BP 60/36'),
            _Result(match_text='O2 sat 97%'),
            _Result(match_text='Wt 3025 grams'),
            _Result(match_text='Lt 18.5 inches'),
            _Result(match_text='HC 35 cm')
        ],
        'Vital signs were T 97.0 BP 85/44 HR 107 RR 28 and SpO2 91% on NRB.':[
            _Result(match_text='T 97.0'),
            _Result(match_text='BP 85/44'),
            _Result(match_text='HR 107'),
            _Result(match_text='RR 28'),
            _Result(match_text='SpO2 91% on NRB'),
        ],
        'Vitals were BP 119/53 (105/43 sleeping) HR 103 RR 15 and ' +\
        'SpO2 97% on NRB.':[
            _Result(match_text='BP 119/53 (105/43'),
            _Result(match_text='HR 103'),
            _Result(match_text='RR 15'),
            _Result(match_text='SpO2 97% on NRB'),
        ],
        'Vitals were Temperature 100.8 Pulse: 103 RR: 28 BP: 84/43 ' +\
        'O2Sat: 88 O2 Flow: 100 (Non-Rebreather).':[
            _Result(match_text='Temperature 100.8'),
            _Result(match_text='Pulse: 103'),
            _Result(match_text='RR: 28'),
            _Result(match_text='BP: 84/43'),
            _Result(match_text='O2Sat: 88'),
            _Result(match_text='O2 Flow: 100 (Non-Rebreather)')
        ],
        'Vitals were T 97.1 HR 76 BP 148/80 RR 25 SpO2 92%/RA.':[
            _Result(match_text='T 97.1'),
            _Result(match_text='HR 76'),
            _Result(match_text='BP 148/80'),
            _Result(match_text='RR 25'),
            _Result(match_text='SpO2 92%/RA'),
        ]
    }

    if not _run_tests(test_data):
        return False

    return True


###############################################################################
def get_version():
    return '{0} {1}.{2}'.format(_MODULE_NAME, _VERSION_MAJOR, _VERSION_MINOR)


###############################################################################
if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Run validation tests on the recognizer modules.'
    )
    
    parser.add_argument('-v', '--version',
                        help='show version and exit',
                        action='store_true')
    parser.add_argument('-d', '--debug',
                        help='print debug information to stdout',
                        action='store_true')

    args = parser.parse_args()

    if 'version' in args and args.version:
        print(_get_version())
        sys.exit(0)

    if 'debug' in args and args.debug:
        lvr.enable_debug()

    lvr.init()
    assert test_lab_value_recognizer()
