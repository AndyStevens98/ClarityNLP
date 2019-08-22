#!/usr/bin/env python3
"""
This is a program for testing the ClarityNLP NLPQL expression evaluator.

It assumes that a run of the NLPQL file 'data_gen.nlpql' has already been
performed. You will need to know the job_id from that run to use this code.

Add your desired expression to the list in _run_tests, then evaluate it using
the data from your ClarityNLP run.
Use this command:

    python3 ./expr_tester.py --jobid <job_id> --mongohost <ip address>
                             --port <port number> --num <number> [--debug]


Help for the command line interface can be obtained via this command:

    python3 ./expr_tester.py --help

Extensive debugging info can be generated with the --debug option.

"""

import re
import os
import sys
import copy
import string
import optparse
import datetime
from pymongo import MongoClient
from collections import namedtuple, OrderedDict
#from bson import ObjectId

import expr_eval
import expr_result
from expr_result import HISTORY_FIELD

_VERSION_MAJOR = 0
_VERSION_MINOR = 4
_MODULE_NAME   = 'expr_tester.py'

_TRACE = False

_TEST_ID            = 'EXPR_TEST'
_TEST_NLPQL_FEATURE = 'EXPR_TEST'


_FILE_DATA_FIELDS = [
    'context',            # value of context variable in NLPQL file
    'names',              # all defined names in the NLPQL file
    'tasks',              # list of ClarityNLP tasks defined in the NLPQL file
    'primitives',         # names actually used in expressions
    'expressions',        # list of (nlpql_feature, string_def) tuples
    'reduced_expressions' # same but with string_def expressed with primitives
]
FileData = namedtuple('FileData', _FILE_DATA_FIELDS)


###############################################################################
def _enable_debug():

    global _TRACE
    _TRACE = True


###############################################################################
def _evaluate_expressions(expr_obj_list,
                          mongo_collection_obj,
                          job_id,
                          context_field,
                          is_final):
    """
    Nearly identical to
    nlp/luigi_tools/phenotype_helper.mongo_process_operations
    """

    phenotype_id    = _TEST_ID
    phenotype_owner = _TEST_ID
        
    assert 'subject' == context_field or 'report_id' == context_field

    all_output_docs = []
    is_final_save = is_final

    for expr_obj in expr_obj_list:

        # the 'is_final' flag only applies to the last subexpression
        if expr_obj != expr_obj_list[-1]:
            is_final = False
        else:
            is_final = is_final_save
        
        # evaluate the (sub)expression in expr_obj
        eval_result = expr_eval.evaluate_expression(expr_obj,
                                                    job_id,
                                                    context_field,
                                                    mongo_collection_obj)
            
        # query MongoDB to get result docs
        cursor = mongo_collection_obj.find({'_id': {'$in': eval_result.doc_ids}})

        # initialize for MongoDB result document generation
        phenotype_info = expr_result.PhenotypeInfo(
            job_id = job_id,
            phenotype_id = phenotype_id,
            owner = phenotype_owner,
            context_field = context_field,
            is_final = is_final
        )

        # generate result documents
        if expr_eval.EXPR_TYPE_MATH == eval_result.expr_type:

            output_docs = expr_result.to_math_result_docs(eval_result,
                                                          phenotype_info,
                                                          cursor)
        else:
            assert expr_eval.EXPR_TYPE_LOGIC == eval_result.expr_type

            # flatten the result set into a set of Mongo documents
            doc_map, oid_list_of_lists = expr_eval.flatten_logical_result(eval_result,
                                                                          mongo_collection_obj)
            
            output_docs = expr_result.to_logic_result_docs(eval_result,
                                                           phenotype_info,
                                                           doc_map,
                                                           oid_list_of_lists)

        if len(output_docs) > 0:
            mongo_collection_obj.insert_many(output_docs)
        else:
            print('mongo_process_operations ({0}): ' \
                  'no phenotype matches on "{1}".'.format(eval_result.expr_type,
                                                          eval_result.expr_text))

        # save the expr object and the results
        all_output_docs.append( (expr_obj, output_docs))

    return all_output_docs


###############################################################################
def _delete_prev_results(job_id, mongo_collection_obj):
    """
    Remove all results in the Mongo collection that were computed by
    expression evaluation. Also remove all temp results from a previous run
    of this code, if any.
    """

    # delete all assigned results from a previous run of this code
    result = mongo_collection_obj.delete_many(
        {"job_id":job_id, "nlpql_feature":_TEST_NLPQL_FEATURE})
    print('Removed {0} result docs with the test feature.'.
          format(result.deleted_count))

    # delete all temp results from a previous run of this code
    result = mongo_collection_obj.delete_many(
        {"nlpql_feature":expr_eval.regex_temp_nlpql_feature})
    print('Removed {0} docs with temp NLPQL features.'.
          format(result.deleted_count))
    

###############################################################################
def banner_print(msg):
    """
    Print the message centered in a border of stars.
    """

    MIN_WIDTH = 79

    n = len(msg)
    
    if n < MIN_WIDTH:
        ws = (MIN_WIDTH - 2 - n) // 2
    else:
        ws = 1

    ws_left = ws
    ws_right = ws

    # add extra space on right to balance if even
    if 0 == n % 2:
        ws_right = ws+1

    star_count = 1 + ws_left + n + ws_right + 1
        
    print('{0}'.format('*'*star_count))
    print('{0}{1}{2}'.format('*', ' '*(star_count-2), '*'))
    print('{0}{1}{2}{3}{4}'.format('*', ' '*ws_left, msg, ' '*ws_right, '*'))
    print('{0}{1}{2}'.format('*', ' '*(star_count-2), '*'))
    print('{0}'.format('*'*star_count))
    
    
###############################################################################
def _run_tests(job_id,
               final_nlpql_feature,
               command_line_expression,
               context_var,
               mongo_collection_obj,
               num,
               is_final,
               name_list=None,
               debug=False):

    global _TRACE

    # names define in data_gen.nlpql; used if expressions are entered on the
    # command line or uncommented in the EXPRESSIONS list below
    NAME_LIST = [
        'hasRigors', 'hasDyspnea', 'hasNausea', 'hasVomiting', 'hasShock',
        'hasTachycardia', 'hasLesion', 'Temperature', 'Lesion',
        'hasFever', 'hasSepsisSymptoms', 'hasTempAndSepsisSymptoms',
        'hasSepsis', 'hasLesionAndSepsisSymptoms', 'hasLesionAndTemp',
        'hasLesionTempAndSepsisSymptoms'
    ]

    EXPRESSIONS = [

        # counts are for job 11222
        
        # all temperature measurements
        # 'Temperature', # 945 results

        # all lesion measurements
        # 'Lesion',      # 2425 results

        # all instances of a temp measurement AND a lesion measurement
        # 'Temperature AND Lesion', # 17 results

        # all instances of the given symptoms
        # 'hasTachycardia', # 1996 results, 757 groups
        # 'hasRigors',      # 683 results, 286 groups
        # 'hasShock',       # 2117 results, 521 groups
        # 'hasDyspnea',     # 3277 results, 783 groups
        # 'hasNausea',      # 2261 results, 753 groups
        # 'hasVomiting',    # 2303 results, 679 groups

        # all instances of a temp measurement and another symptom
        # 'Temperature AND hasTachycardia', # 55 results, 13 groups
        # 'Temperature AND hasRigors',      # 11 results, 5 groups
        # 'Temperature AND hasShock',       # 50 results, 11 groups
        # 'Temperature AND hasDyspnea',     # 64 results, 11 groups
        # 'Temperature AND hasNausea',      # 91 results, 17 groups
        # 'Temperature AND hasVomiting',    # 74 results, 13 groups

        # all instances of a lesion measurement and another symptom
        # 'Lesion AND hasTachycardia', # 131 results, 24 groups
        # 'Lesion AND hasRigors',      # 50 results, 11 groups
        # 'Lesion AND hasShock',       # 43 results, 10 groups
        # 'Lesion AND hasDyspnea',     # 103 results, 21 groups
        # 'Lesion AND hasNausea',      # 136 results, 30 groups
        # 'Lesion AND hasVomiting',    # 150 results, 26 groups

        # pure math expressions
        # 'Temperature.value >= 100.4',    # 488 results
        # 'Temperature.value >= 1.004e2',  # 488 results
        # '100.4 <= Temperature.value',    # 488 results
        # '(Temperature.value >= (100.4))',  # 488 results
        # 'Temperature.value == 100.4',    # 14 results
        # 'Temperature.value + 3 ^ 2 < 109',      # temp < 100,     374 results
        # 'Temperature.value ^ 3 + 2 < 941194',   # temp < 98,      118 results
        # 'Temperature.value % 3 ^ 2 == 2',       # temp == 101,    68 results
        # 'Temperature.value * 4 ^ 2 >= 1616',    # temp >= 101,    417 results
        # 'Temperature.value / 98.6 ^ 2 < 0.01',  # temp < 97.2196, 66 results
        # '(Temperature.value / 98.6)^2 < 1.02',  # temp < 99.581,  325 results
        # '0 == Temperature.value % 20',          # temp == 100,    40 results
        # '(Lesion.dimension_X <= 5) OR (Lesion.dimension_X >= 45)',           # 746 results
        # 'Lesion.dimension_X > 15 AND Lesion.dimension_X < 30',               # 528 results
        # '((Lesion.dimension_X) > (15)) AND (((Lesion.dimension_X) < (30)))', # 528 results

        # math involving multiple NLPQL features
        # 'Lesion.dimension_X > 15 AND Lesion.dimension_X < 30 OR (Temperature.value >= 100.4)', # 1016 results
        # '(Lesion.dimension_X > 15 AND Lesion.dimension_X < 30) AND Temperature.value > 100.4', # 2 results
        # 'Lesion.dimension_X > 15 AND Lesion.dimension_X < 30 AND Temperature.value > 100.4', # 2 results

        # need to remove duplicate results for the same patient?? TBD
        # '(Temperature.value >= 102) AND (Lesion.dimension_X <= 5)',  # 4 results
        # '(Temperature.value >= 102) AND (Lesion.dimension_X <= 5) AND (Temperature.value >= 103)', # 2 results

        # pure logic
        # 'hasTachycardia AND hasShock',                  # 191 results, 25 groups
        # 'hasTachycardia OR hasShock',                   # 4113 results, 1253 groups
        # 'hasTachycardia NOT hasShock',                  # 1891 results, 732 groups
        # '(hasTachycardia AND hasDyspnea) NOT hasRigors' # 229 results, 46 groups
        # 'hasTachycardia AND hasDyspnea',                # 240 results, 49 groups
        # '((hasShock) AND (hasDyspnea))',                # 155 results, 22 groups
        # '((hasTachycardia) AND (hasRigors OR hasDyspnea OR hasNausea))', # 546 results, 112 groups
        # '((hasTachycardia)AND(hasRigorsORhasDyspneaORhasNausea))',       # 546 results, 112 groups
        # 'hasTachycardia NOT (hasRigors OR hasDyspnea)',   # 1800 results, 683 groups
        # 'hasTachycardia NOT (hasRigors OR hasDyspnea OR hasNausea)',     # 1702 results, 645 groups
        # 'hasTachycardia NOT (hasRigors OR hasDyspnea OR hasNausea or hasVomiting)', # 1622 results, 619 groups
        # 'hasTachycardia NOT (hasRigors OR hasDyspnea OR hasNausea OR hasVomiting OR hasShock)', # 1529r, 599 g
        # 'hasTachycardia NOT (hasRigors OR hasDyspnea OR hasNausea OR hasVomiting OR hasShock ' \
        # 'OR Temperature)', # 1491 results, 589 groups
        # 'hasTachycardia NOT (hasRigors OR hasDyspnea OR hasNausea OR hasVomiting OR hasShock ' \
        # 'OR Temperature OR Lesion)', # 1448 results, 569 groups

        # 'hasTachycardia NOT (hasRigors AND hasDyspnea)',  # 1987 results, 754 groups
        # 'hasRigors AND hasTachycardia AND hasDyspnea',    # 11 results, 3 groups
        # 'hasRigors AND hasDyspnea AND hasTachycardia',    # 11 results, 3 groups
        # 'hasRigors OR hasTachycardia AND hasDyspnea',     # 923 results, 332 groups
        # '(hasRigors OR hasDyspnea) AND hasTachycardia',   # 340 results, 74 groups
        # 'hasRigors AND (hasTachycardia AND hasNausea)',   # 22 results, 5 groups
        # '(hasShock OR hasDyspnea) AND (hasTachycardia OR hasNausea)', # 743 results, 129 groups
        # '(hasShock OR hasRigors) NOT (hasTachycardia OR hasNausea)', # 2468 results, 705 groups
        
        # 'Temperature AND (hasDyspnea OR hasTachycardia)',  # 106 results, 22 groups
        # 'Lesion AND (hasDyspnea OR hasTachycardia)',       # 234 results, 45 groups

        # mixed math and logic 
        # 'hasNausea AND Temperature.value >= 100.4', # 73 results, 16 groups
        # 'Lesion AND hasRigors',                     # 50 results, 11 groups
        # 'Lesion.dimension_X < 10 AND hasRigors',    # 19 results, 7 groups
        # 'Lesion.dimension_X < 10',                  # 841 results
        # 'Lesion.dimension_X < 10 OR hasRigors',     # 1524 results, 633 groups
        # '(hasRigors OR hasTachycardia OR hasNausea OR hasVomiting or hasShock) AND ' \
        # '(Temperature.value >= 100.4)',             # 180 results, 38 groups

        # 1808 results, 702 groups
        # 'Lesion.dimension_X > 10 AND Lesion.dimension_X < 30 OR (hasRigors OR hasTachycardia AND hasDyspnea)',

        # 6841 results, 2072 groups
        # 'Lesion.dimension_X > 10 AND Lesion.dimension_X < 30 OR hasRigors OR hasTachycardia OR hasDyspnea',

        # 797 results, 341 groups
        # '(Lesion.dimension_X > 10 AND Lesion.dimension_X < 30) NOT (hasRigors OR hasTachycardia OR hasDyspnea)',

        # 'Temperature AND hasDyspnea AND hasNausea AND hasVomiting', # 22 results, 2 groups
        # '(Temperature.value > 100.4) AND hasDyspnea AND hasNausea AND hasVomiting', # 20 results, 2 groups
        # 692 results, 287 groups
        # 'hasRigors OR (hasTachycardia AND hasDyspnea) AND Temperature.value >= 100.4',
        # 155 results, 33 groups
        # '(hasRigors OR hasTachycardia OR hasDyspnea OR hasNausea) AND Temperature.value >= 100.4',
        # 'Lesion.dimension_X < 10 OR hasRigors AND Lesion.dimension_X > 30', # 851 results, 356 groups

        # redundant math expressions
        # 'Lesion.dimension_X > 50',  # 246 results
        # 'Lesion.dimension_X > 30 AND Lesion.dimension_X > 50',  # 246 results
        # 'Lesion.dimension_X > 12 AND Lesion.dimension_X > 30 AND Lesion.dimension_X > 50', # 246 results
        # '(Lesion.dimension_X > 50) OR (hasNausea AND hasDyspnea)', # 518 results, 195 groups
        # 518 results, 195 groups
        # '(Lesion.dimension_X > 30 AND Lesion.dimension_X > 50) OR (hasNausea AND hasDyspnea)',
        # 518 results, 195 groups
        # '(Lesion.dimension_X > 12 AND Lesion.dimension_X > 50) OR (hasNausea AND hasDyspnea)',
        # 518 results, 195 groups
        # '(Lesion.dimension_X > 12 AND Lesion.dimension_X > 30 AND Lesion.dimension_X > 50) OR '
        # '(hasNausea AND hasDyspnea)',
        
        # 'Lesion.dimension_X > 10 AND Lesion.dimension_X < 30', # 885 results
        # 'Lesion.dimension_X > 5 AND Lesion.dimension_X > 10 AND ' \
        # 'Lesion.dimension_X < 40 AND Lesion.dimension_X < 30',   # 885 results
        # '(Lesion.dimension_X > 8 AND Lesion.dimension_X > 5 AND Lesion.dimension_X > 10) AND '
        # '(Lesion.dimension_X < 40 AND Lesion.dimension_X < 30 AND Lesion.dimension_X < 45)', # 885 results

        # checking NOT with positive logic
        
        #  of this group of four, the final two expressions are identical
        # '(hasRigors OR hasDyspnea OR hasTachycardia) AND Temperature', # 117 results, 25 groups
        # '(hasRigors OR hasDyspnea OR hasTachycardia) AND (Temperature.value >= 100.4)', # 82 results, 20 groups
        # '(hasRigors OR hasDyspnea OR hasTachycardia) AND (Temperature.value < 100.4)',  # 53 results, 10 groups
        # '(hasRigors OR hasDyspnea OR hasTachycardia) NOT (Temperature.value >= 100.4)', # 53 results, 10 groups

        # final two in this group should be identical
        # '(hasRigors OR hasDyspnea) AND Temperature', # 75 results, 14 groups
        # '(hasRigors OR hasDyspnea) AND (Temperature.value >= 99.5 AND Temperature.value <= 101.5)', # 34r, 7g
        # '(hasRigors OR hasDyspnea) NOT (Temperature.value < 99.5  OR  Temperature.value > 101.5)', # 34r, 7g

        
        # Checking the behavior of NOT with set theory relations:
        #
        #     Let P == probability, or for our purposes here, the unique element count in a given set.
        #
        #     'Groups' refers to grouping the results on the value of the context variable, which
        #     is either the document ID or patient ID. So the group count is the number of distinct
        #     values of the context variable (the unique docs or unique patients).
        #
        #     'Results' refers to the rows of output in the CSV file. This will vary with the
        #     form of the expression and will contain some amount of redundancy. The redundancy
        #     is required to flatten the data into a row-based spreadsheet format. What matters
        #     is the UNIQUE data per patient or document, which is why groups are more important.
        #
        #     The set relations of interest are (think of Venn diagrams):
        #
        #     P(A OR B) == P(A) + P(B) - P(A AND B)
        # 
        #     P(A OR B OR C) == P(A) + P(B) + P(C) - (P(A AND B) + P(A AND C) + P(B AND C)) + P(A AND B AND C)
        #
        # If 'Groups' denotes the number of context variable groups in the expression evaluator result,
        # these relations should hold:
        #
        #     Groups[A OR B] == Groups[A] + Groups[B] - Groups[A AND B]
        #     Groups[A OR B] == Groups[(A OR B) NOT (A AND B)] + Groups[A AND B]
        #
        #     Groups[A OR B OR C] == Groups[A] + Groups[B] + Groups[C] -
        #                            ( Groups[A AND B] + Groups[A AND C] + Groups[B AND C] ) +
        #                            Groups[ A AND B AND C ]
        #
        #     For the second relation, we need to evaluate this expression:
        #
        #         (A OR B OR C) NOT ( (A AND B) OR (A AND C) OR (B AND ) ) OR (A AND B AND C)
        #
        #     This needs to be rearranged into this equivalent form, to make sure the NOT applies to ALL the
        #     available docs, and to prevent dependencies on the evaluation order:
        #
        #         ((A OR B OR C) OR (A AND B AND C)) NOT ( (A AND B) OR (A AND C) OR (B AND C) )
        #
        #     The subexpression prior to the NOT is an OR of two terms. There could be duplicates between these two
        #     sets, so the duplicates need to be subtracted out as well. A direct evaluation of this expression will
        #     give the minimal result set PLUS any duplicates between (A OR B OR C) and (A AND B AND C).
        #
        #     Thus the relation for the second check becomes:
        #
        #     Groups[A OR B OR C] == Groups[ ((A OR B OR C) OR (A AND B AND C)) NOT ((A AND B) OR (A AND C) OR (B AND C) )] +
        #                            Groups[A AND B] + Groups[A AND C] + Groups[B AND C] -
        #                            Groups[A AND B AND C] -
        #                            Groups[ (A OR B OR C) AND (A AND B AND C) ]
        #
        #     In the expressions below, anything contained in single quotes is sent to the evaluator.
        #

        # 1. hasRigors OR hasDyspnea
        # ----------------------------
        '(hasRigors OR hasDyspnea)', # 3960 results, 1048 groups direct evaluation
        # 'hasRigors',                 # 683 results, 286 groups
        # 'hasDyspnea',                # 3277 results, 783 groups
        # 'hasRigors AND hasDyspnea',  # 89 results, 21 groups
        # '(hasRigors OR hasDyspnea) NOT (hasRigors AND hasDyspnea)', # 3825 results, 1027 groups
        # group check 1:  Groups[hasRigors] + Groups[hasDyspnea] - Groups[hasRigors AND hasDyspnea]
        #                   286 + 783 - 21 = 1048, identical to Groups[hasRigors OR hasDyspnea]
        # group check 2:  Groups[(hasRigors OR hasDyspnea) NOT (hasRigors AND hasDyspnea)] + Groups[hasRigors AND hasDyspnea]
        #                   1027 + 21 = 1048 groups, identical to Groups[hasRigors OR hasDyspnea]

        # 2. hasTachycardia OR hasShock
        # -------------------------------
        # 'hasTachycardia OR hasShock',  # 4113 results, 1253 groups direct evaluation
        # 'hasTachycardia',              # 1996 results, 757 groups
        # 'hasShock',                    # 2117 results, 521 groups
        # 'hasTachycardia AND hasShock', # 191 results, 25 groups
        # '(hasTachycardia OR hasShock) NOT (hasTachycardia AND hasShock)', # 3867 results, 1228 groups
        # group check 1: Groups[hasTachycardia] + Groups[hasShock] - Groups[hasTachycardia AND hasShock]
        #                  757 + 521 - 25 = 1253, identical to Groups[hasTachycardia OR hasShock]
        # group check 2: Groups[(hasTachycardia OR hasShock) NOT (hasTachycardia AND hasShock)] + Groups[hasTachycardia AND hasShock]
        #                 1228 + 25 = 1253, identical to Groups[hasTachycardia OR hasShock]

        # 3. hasShock OR hasDyspnea OR hasTachycardia
        # -------------------------------------------
        # 'hasShock OR hasDyspnea OR hasTachycardia',     # 7390 results, 1967 groups
        # 'hasShock',                                     # 2117 results, 521 groups
        # 'hasDyspnea',                                   # 3277 results, 783 groups
        # 'hasTachycardia',                               # 1996 results, 757 groups
        # 'hasShock AND hasDyspnea',                      # 155 results, 22 groups
        # 'hasShock AND hasTachycardia',                  # 191 results, 25 groups
        # 'hasDyspnea AND hasTachycardia',                # 240 results, 49 groups
        # 'hasShock AND hasDyspnea AND hasTachycardia',   # 11 results, 2 groups
        # '((hasShock OR hasDyspnea OR hasTachycardia) OR (hasShock AND hasDyspnea AND hasTachycardia)) NOT ( (hasShock AND hasDyspnea) OR (hasShock AND hasTachycardia) OR (hasDyspnea AND hasTachycardia) )' # 6607 results, 1875 groups
        # '((hasShock OR hasDyspnea OR hasTachycardia) AND (hasShock AND hasDyspnea AND hasTachycardia))', # 20 results, 2 groups
        # group check 1: Groups[hasShock] + Groups[hasDyspnea] + Groups[hasTachycardia] -
        #                (Groups[hasShock AND hasDyspnea] + Groups[hasShock AND hasTachycardia] + Groups[hasDyspnea AND hasTachycardia]) +
        #                Groups[hasShock + hasDyspnea + hasTachycardia]
        #                521 + 783 + 757 - (22 + 25 + 49) + 2 = 1967 groups, identical to Groups[hasShock OR hasDyspnea OR hasTachycardia]
        # group check 2: Groups[((shock OR dysp OR tachy) OR (shock AND dysp AND tachy)) NOT ( (shock AND dysp) OR (shock AND tachy) OR (dysp AND tachy)] +
        #                Groups[shock and dysp] + Groups[shock and tachy] + Groups[dysp and tachy] -
        #                Groups[shock AND dysp AND tachy] -
        #                Groups[(shock OR dysp OR tachy) AND (shock AND dysp AND tachy)]
        #                1875 + 22 + 25 + 49 - 2 - 2 = 1967 groups, identical to Groups[hasShock OR hasDyspnea OR hasTachycardia]

        # 4. hasTachycardia OR hasShock OR hasRigors
        # ------------------------------------------
        # 'hasTachycardia OR hasShock OR hasRigors',   # 4796 results, 1502 groups
        # 'hasTachycardia',                            # 1996 results, 757 groups
        # 'hasShock',                                  # 2117 results, 521 groups
        # 'hasRigors',                                 # 683 results, 286 groups
        # 'hasTachycardia AND hasShock',               # 191 results, 25 groups
        # 'hasTachycardia AND hasRigors',              # 104 results, 28 groups
        # 'hasShock AND hasRigors',                    # 52 results, 11 groups
        # 'hasTachycardia AND hasShock AND hasRigors', # 11 results, 2 groups
        # '((hasTachycardia OR hasShock OR hasRigors) OR (hasTachycardia AND hasShock AND hasRigors)) NOT ( (hasTachycardia AND hasShock) OR (hasTachycardia AND hasRigors) OR (hasShock AND hasRigors) )', # 4338 results, 1442 groups
        # '((hasTachycardia OR hasShock OR hasRigors) AND (hasTachycardia AND hasShock AND hasRigors))', # 22 results, 2 groups
        # group check 1: 757 + 521 + 286 - (25 + 28 + 11) + 2 = 1502 groups, identical to direct eval
        # group check 2: 1442 + 25 + 28 + 11 - 2 - 2 = 1502 groups, identical to direct eval

        #     Groups[A OR B] == Groups[A] + Groups[B] - Groups[A AND B]
        #     Groups[A OR B] == Groups[(A OR B) NOT (A AND B)] + Groups[A AND B]
        
        # the same, but group as (hasTachycardia OR hasShock) OR hasRigors and use two-component formula
        # ----------------------------------------------------------------------------------------------
        # 'hasTachycardia OR hasShock',                 # 4113 results, 1253 groups
        # 'hasRigors',                                  # 683 results, 286 groups
        # '(hasTachycardia OR hasShock) AND hasRigors', # 152 results, 37 groups
        # '((hasTachycardia OR hasShock) OR hasRigors) NOT ( (hasTachycardia OR hasShock) AND hasRigors)', # 4568 results, 1465 groups
        # group check 1: Groups[hasTachycardia OR hasShock] + Groups[hasRigors] - Groups[(hasTachycardia OR hasShock) AND hasRigors]
        #                  1253 + 286 - 37 == 1502 groups, identical to Groups[hasTachycardia OR hasShock OR hasRigors]
        # group check 2: Groups[((hasTachycardia OR hasShock) OR hasRigors) NOT ( (hasTachycardia OR hasShock) AND hasRigors)] + Groups[(hasTachycardia OR hasShock) AND hasRigors]
        #                  1465 + 37 = 1502 groups, identical to Groups[hasTachycardia OR hasShock OR hasRigors]

        # the same, but group as hasTachycardia OR (hasShock OR hasRigors) and use two-component formula
        # ----------------------------------------------------------------------------------------------
        # 'hasTachycardia',                             # 1996 results, 757 groups
        # 'hasShock OR hasRigors',                      # 2800 results, 796 groups
        # 'hasTachycardia AND (hasShock OR hasRigors)', # 292 results, 51 groups
        # '(hasTachycardia OR (hasShock OR hasRigors)) NOT ( hasTachycardia AND (hasShock OR hasRigors) )', # 4402 results, 1451 groups
        # group check 1: Groups[hasTachycardia] + Groups[hasShock or hasRigors] - Groups[hasTachycardia AND (hasShock OR hasRigors)]
        #                  757 + 796 - 51 = 1502 groups, identical to Groups[hasTachycardia OR hasShock OR hasRigors]
        # group check 2: Groups[(hasTachycardia OR (hasShock OR hasRigors)) NOT ( hasTachycardia AND (hasShock OR hasRigors) )] + Groups[hasTachycardia AND (hasShock OR hasRigors)]
        #                  1451 + 51 = 1502 groups, identical to Groups[hasTachycardia OR hasShock OR hasRigors]

        # 5. hasRigors OR hasDyspnea OR (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10), mixed logic and math
        # ----------------------------------------------------------------------------------------------------------
        # 'hasRigors OR hasDyspnea OR (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)',   # 4028 results, 1104 groups
        # 'hasRigors',                                                                           # 683 results, 286 groups
        # 'hasDyspnea',                                                                          # 3277 results, 783 groups
        # '(Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)',                              # 67 results, 57 groups
        # 'hasRigors AND hasDyspnea',                                                            # 89 results, 21 groups
        # 'hasRigors AND (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)',                # 0 results, 0 groups
        # 'hasDyspnea AND (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)',               # 5 results, 1 group
        # 'hasRigors AND hasDyspnea AND (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)', # 0 results, 0 groups
        # # 3886 results, 1082 groups
        # '((hasRigors OR hasDyspnea OR (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)) OR (hasRigors AND hasDyspnea AND (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10))) ' \
        # 'NOT( (hasRigors AND hasDyspnea) OR (hasRigors AND (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)) OR (hasDyspnea AND (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)))'
        # 0 results, 0 groups
        # '((hasRigors OR hasDyspnea OR (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)) AND (hasRigors AND hasDyspnea AND (Lesion.dimension_X >= 10 AND Lesion.dimension_Y < 10)))',
        # group check 1: 286 + 783 + 57 - (21 + 0 + 1) + 0 = 1104 groups, expected result
        # group check 2: 1082 + 21 + 0 + 1 - 0 - 0 = 1104 groups, expected result
        
        # should generate a parser exception
        # 'This is junk and should cause a parser exception',

        # not a valid expression, since each math expression must produce a Boolean result
        # '(Temp.value/98.6) * (HR.value/60.0) * (BP.systolic/110) < 1.1',
    ]

    # must either be a patient or document context
    context_var = context_var.lower()
    assert 'patient' == context_var or 'document' == context_var

    if 'patient' == context_var:
        context_field = 'subject'
    else:
        context_field = 'report_id'

    # cleanup so that database only contains data generated by data_gen.nlpql
    # not from previous runs of this test code
    _delete_prev_results(job_id, mongo_collection_obj)

    if debug:
        _enable_debug()
        expr_eval.enable_debug()

    # get all defined names, helps resolve tokens if bad expression formatting
    the_name_list = NAME_LIST
    if name_list is not None:
        the_name_list = name_list

    if command_line_expression is None:
        expressions = EXPRESSIONS
    else:
        expressions = [command_line_expression]
        
    counter = 1
    for e in expressions:

        print('[{0:3}]: "{1}"'.format(counter, e))

        parse_result = expr_eval.parse_expression(e, the_name_list)
        if 0 == len(parse_result):
            print('\n*** parse_expression failed ***\n')
            break
        
        # generate a list of ExpressionObject primitives
        expression_object_list = expr_eval.generate_expressions(final_nlpql_feature,
                                                                parse_result)
        if 0 == len(expression_object_list):
            print('\n*** generate_expressions failed ***\n')
            break
        
        # evaluate the ExpressionObjects in the list
        results = _evaluate_expressions(expression_object_list,
                                        mongo_collection_obj,
                                        job_id,
                                        context_field,
                                        is_final)

        banner_print(e)
        for expr_obj, output_docs in results:
            print()
            print('Subexpression text: {0}'.format(expr_obj.expr_text))
            print('Subexpression type: {0}'.format(expr_obj.expr_type))
            print('      Result count: {0}'.format(len(output_docs)))
            print('     NLPQL feature: {0}'.format(expr_obj.nlpql_feature))
            print('\nResults: ')

            n = len(output_docs)
            if 0 == n:
                print('\tNone.')
                continue

            if expr_eval.EXPR_TYPE_MATH == expr_obj.expr_type:
                for k in range(n):
                    if k < num or k > n-num:
                        doc = output_docs[k]
                        print('[{0:6}]: Document ...{1}, NLPQL feature {2}:'.
                              format(k, str(doc['_id'])[-6:],
                                     expr_obj.nlpql_feature))
                        
                        if 'history' in doc:
                            assert 1 == len(doc['history'])
                            data_field = doc['history'][0].data
                        else:
                            data_field = doc['value']

                        if 'subject' == context_field:
                            context_str = 'subject: {0:8}'.format(doc['subject'])
                        else:
                            context_str = 'report_id: {0:8}'.format(doc['report_id'])
                            
                        print('\t[{0:6}]: _id: {1} nlpql_feature: {2:16} ' \
                              '{3} data: {4}'.
                              format(k, doc['_id'], doc['nlpql_feature'],
                                     context_str, data_field))
                    elif k == num:
                        print('\t...')

            else:
                for k in range(n):
                    if k < num or k > n-num:
                        doc = output_docs[k]
                        print('[{0:6}]: Document ...{1}, NLPQL feature {2}:'.
                              format(k, str(doc['_id'])[-6:],
                                     expr_obj.nlpql_feature))

                        history = doc[HISTORY_FIELD]
                        for tup in history:
                            if isinstance(tup.data, float):

                            # format data depending on whether float or string
                                data_string = '{0:<10}'.format(tup.data)
                            else:
                                data_string = '{0}'.format(tup.data)

                            if 'subject' == context_field:
                                context_str = 'subject: {0:8}'.format(tup.subject)
                            else:
                                context_str = 'report_id: {0:8}'.format(tup.report_id)

                            print('\t\t_id: ...{0} operation: {1:20} '  \
                                  'nlpql_feature: {2:16} {3} ' \
                                  'data: {4} '.
                                  format(str(tup.oid)[-6:], tup.pipeline_type,
                                         tup.nlpql_feature, context_str,
                                         data_string))
                    elif k == num:
                        print('\t...')
                
        counter += 1
        print()

        # exit if user provided an expression on the command line
        if command_line_expression is not None:
            break

    return True


###############################################################################
def _reduce_expressions(file_data):

    # this needs to be done after token resolution with the name_list
    # also need whitespace between all tokens
    # (expr_eval.is_valid)

    if _TRACE:
        print('called _reduce_expressions...')
    
    task_names = set(file_data.tasks)
    defined_names = set(file_data.names)
    
    expr_dict = OrderedDict()
    for expr_name, expr_def in file_data.expressions:
        expr_dict[expr_name] = expr_def

    all_primitive = False
    while not all_primitive:
        all_primitive = True
        for expr_name, expr_def in expr_dict.items():
            tokens = expr_def.split()
            is_composite = False
            for index, token in enumerate(tokens):
                # only want NLPQL-defined names
                if token not in defined_names:
                    #print('not in defined_names: {0}'.format(token))
                    continue
                elif token in task_names:
                    # cannot reduce further
                    #print('Expression "{0}": primitive name "{1}"'.
                    #      format(expr_name, token))
                    continue
                elif token != expr_name and token in expr_dict:
                    is_composite = True
                    #print('Expression "{0}": composite name "{1}"'.
                    #      format(expr_name, token))
                    # expand and surround with space-separated parens
                    new_token = '( ' + expr_dict[token] + r' )'
                    tokens[index] = new_token
            if is_composite:
                expr_dict[expr_name] = ' '.join(tokens)
                all_primitive = False

    # scan RHS of each expression and ensure expressed entirely in primitives
    primitives = set()
    for expr_name, expr_def in expr_dict.items():
        tokens = expr_def.split()
        for token in tokens:
            if -1 != token.find('.'):
                nlpql_feature, field = token.split('.')
            else:
                nlpql_feature = token
            if token not in defined_names:
                continue
            assert nlpql_feature in task_names
            primitives.add(nlpql_feature)

    assert 0 == len(file_data.reduced_expressions)
    for expr_name, reduced_expr in expr_dict.items():
        file_data.reduced_expressions.append( (expr_name, reduced_expr) )
    assert len(file_data.reduced_expressions) == len(file_data.expressions)
    
    assert 0 == len(file_data.primitives)
    for p in primitives:
        file_data.primitives.append(p)
        
    return file_data


###############################################################################
def _parse_file(filepath):
    """
    Read the NLPQL file and extract the context, nlpql_features, and 
    associated expressions. Returns a FileData namedtuple.
    """

    # repeated whitespace replaced with single space below, so can use just \s
    str_context_statement = r'context\s(?P<context>[^;]+);'
    regex_context_statement = re.compile(str_context_statement)

    str_expr_statement = r'\bdefine\s(final\s)?(?P<feature>[^:]+):\s'  +\
                         r'where\s(?P<expr>[^;]+);'
    regex_expr_statement = re.compile(str_expr_statement, re.IGNORECASE)

    # ClarityNLP task statements have no 'where' clause
    str_task_statement = r'\bdefine\s(final\s)?(?P<feature>[^:]+):\s(?!where)'
    regex_task_statement = re.compile(str_task_statement, re.IGNORECASE)
    
    with open(filepath, 'rt') as infile:
        text = infile.read()

    # strip comments
    text = re.sub(r'//[^\n]+\n', ' ', text)

    # replace newlines with spaces for regex simplicity
    text = re.sub(r'\n', ' ', text)

    # replace repeated spaces with a single space
    text = re.sub(r'\s+', ' ', text)

    # extract the context
    match = regex_context_statement.search(text)
    if match:
        context = match.group('context').strip()
    else:
        print('*** parse_file: context statement not found ***')
        sys.exit(-1)

    # extract expression definitions
    expression_dict = OrderedDict()
    iterator = regex_expr_statement.finditer(text)
    for match in iterator:
        feature = match.group('feature').strip()
        expression = match.group('expr').strip()
        if feature in expression_dict:
            print('*** parse_file: multiple definitions for "{0}" ***'.
                  format(feature))
            sys.exit(-1)
        expression_dict[feature] = expression

    # extract task definitions
    task_list = []
    iterator = regex_task_statement.finditer(text)
    for match in iterator:
        task = match.group('feature').strip()
        if task in task_list:
            print('*** parse_file: multiple definitions for "{0}" ***'.
                  format(task))
            sys.exit(-1)
        task_list.append(task)

    # check task names to ensure not also an expression name
    for t in task_list:
        if t in expression_dict:
            print('*** parse_file: multiple definitions for "{0}" ***'.
                  format(t))
            sys.exit(-1)

    # build list of all names
    name_list = []
    for task_name in task_list:
        name_list.append(task_name)
    for expression_name in expression_dict.keys():
        name_list.append(expression_name)

    file_data = FileData(
        context = context,
        names = name_list,
        primitives = [],   # computed later
        tasks = task_list,
        reduced_expressions = [],
        expressions = [ (expr_name, expr_def) for
                        expr_name,expr_def in expression_dict.items()]
    )

    # reduce the expressions to their most primitive form
    file_data = _reduce_expressions(file_data)

    if _TRACE:
        print('FILE DATA AFTER EXPRESSION REDUCTION: ')
        print('\t  context:  {0}'.format(file_data.context))
        print('\ttask_names: {0}'.format(file_data.tasks))
        print('\t     names: {0}'.format(file_data.names))
        print('\tprimitives: {0}'.format(file_data.primitives))
        print('\texpressions: ')
        for i in range(len(file_data.expressions)):
            expr_name, expr_def = file_data.expressions[i]
            expr_name, expr_reduced = file_data.reduced_expressions[i]
            print('{0}'.format(expr_name))
            print('\toriginal: {0}'.format(expr_def))
            print('\t reduced: {0}'.format(expr_reduced))

    sys.exit(0)
    return file_data
        

###############################################################################
def _get_version():
    return '{0} {1}.{2}'.format(_MODULE_NAME, _VERSION_MAJOR, _VERSION_MINOR)


###############################################################################
def _show_help():
    print(_get_version())
    print("""
    USAGE: python3 ./{0} --jobid <integer> [-cdhvmpnef]

    OPTIONS:

        -j, --jobid    <integer>   job_id of data in MongoDB
        -c, --context  <string>    either 'patient' or 'document'
                                   (default is patient)
        -m, --mongohost            IP address of remote MongoDB host
                                   (default is localhost)
        -p, --port                 port number for remote MongoDB host
                                   (default is 27017)

        -n, --num                  Number of results to display at start and
                                   end of results array (the number of results
                                   displayed is 2 * n). Default is n == 16.

        -f, --file                 NLPQL file to process. Must contain only 
                                   define statements. If this option is present
                                   the -e option cannot be used.

        -e, --expr                 NLPQL expression to evaluate.
                                   (default is to use a test expression from this file)
                                   If this option is present the -f option
                                   cannot be used.
    FLAGS:

        -h, --help           Print this information and exit.
        -d, --debug          Enable debug output.
        -v, --version        Print version information and exit.
        -i, --isfinal        Generate NLPQL 'final' result. Default is to
                             generate an 'intermediate' result.

    """.format(_MODULE_NAME))


###############################################################################
if __name__ == '__main__':

    optparser = optparse.OptionParser(add_help_option=False)
    optparser.add_option('-c', '--context', action='store', dest='context')
    optparser.add_option('-j', '--jobid', action='store', dest='job_id')
    optparser.add_option('-d', '--debug', action='store_true',
                         dest='debug', default=False)
    optparser.add_option('-v', '--version',
                         action='store_true', dest='get_version')
    optparser.add_option('-h', '--help',
                         action='store_true', dest='show_help', default=False)
    optparser.add_option('-i', '--isfinal',
                         action='store_true', dest='isfinal', default=False)
    optparser.add_option('-m', '--mongohost', action='store', dest='mongohost')
    optparser.add_option('-p', '--port', action='store', dest='port')
    optparser.add_option('-n', '--num', action='store', dest='num')
    optparser.add_option('-e', '--expr', action='store', dest='expr')
    optparser.add_option('-f', '--file', action='store', dest='filepath')

    opts, other = optparser.parse_args(sys.argv)

    if opts.show_help or 1 == len(sys.argv):
        _show_help()
        sys.exit(0)

    if opts.get_version:
        print(_get_version())
        sys.exit(0)

    debug = False
    if opts.debug:
        debug = True
        _enable_debug()

    if opts.job_id is None:
        print('The job_id (-j command line option) must be provided.')
        sys.exit(-1)
    job_id = int(opts.job_id)

    mongohost = 'localhost'
    if opts.mongohost is not None:
        mongohost = opts.mongohost

    port = 27017
    if opts.port is not None:
        port = int(opts.port)

    is_final = opts.isfinal

    context = 'patient'
    if opts.context is not None:
        context = opts.context

    num = 16
    if opts.num is not None:
        num = int(opts.num)

    expr = None
    if opts.expr is not None:
        if opts.filepath is not None:
            print('Options -e and -f are mutually exclusive.')
            sys.exit(-1)
        else:
            expr = opts.expr

    filepath = None
    name_list = None
    if opts.filepath is not None:
        if opts.expr is not None:
            print('Options -e and -f are mutually exclusive.')
            sys.exit(-1)
        else:
            filepath = opts.filepath
            if not os.path.exists(filepath):
                print('File not found: "{0}"'.format(filepath))
                sys.exit(-1)
            file_data = _parse_file(filepath)
            name_list = file_data.names

    # connect to ClarityNLP mongo collection nlp.phenotype_results
    mongo_client_obj = MongoClient(mongohost, port)
    mongo_db_obj = mongo_client_obj['nlp']
    mongo_collection_obj = mongo_db_obj['phenotype_results']

    # delete any data computed from NLPQL expressions, will recompute
    # the task data is preserved
    if filepath is not None:
        for nlpql_feature, expression in file_data.expressions:

            result = mongo_collection_obj.delete_many({"job_id":job_id,
                                                       "nlpql_feature":nlpql_feature})
            print('Removed {0} docs with NLPQL feature {1}.'.
                  format(result.deleted_count, nlpql_feature))

    if filepath is None:
        # command-line expression uses the test feature
        final_nlpql_feature = _TEST_NLPQL_FEATURE
    
        _run_tests(job_id,
                   final_nlpql_feature,
                   expr,
                   context,
                   mongo_collection_obj,
                   num,
                   is_final,
                   name_list,
                   debug)
    else:
        # compute all expressions defined in the NLPQL file
        context = file_data.context
        for nlpql_feature, expression in file_data.expressions:
            _run_tests(job_id,
                       nlpql_feature,
                       expression,
                       context,
                       mongo_collection_obj,
                       num,
                       is_final,
                       name_list,
                       debug)
            
