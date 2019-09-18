#!/usr/bin/env python3
"""
Module used to decode JSON results from the FHIR CQL wrapper.
"""

import re
import os
import sys
import json
import base64
import argparse
from collections import namedtuple
from datetime import datetime, timezone, timedelta, time

if __name__ == '__main__':
    # modify path for local testing
    cur_dir = sys.path[0]
    nlp_dir, tail = os.path.split(cur_dir)
    sys.path.append(nlp_dir)
    sys.path.append(os.path.join(nlp_dir, 'algorithms', 'finder'))    
    import time_finder    
    from flatten import flatten
else:
    from data_access.flatten import flatten
    from algorithms.finder import time_finder

# exported for result display
KEY_VALUE_NAME    = 'value_name'
KEY_VALUE         = 'value'
KEY_UNITS         = 'unit'
KEY_DATE_TIME     = 'date_time'
KEY_END_DATE_TIME = 'end_date_time'
    
_VERSION_MAJOR = 0
_VERSION_MINOR = 7
_MODULE_NAME   = 'cql_result_parser.py'

# set to True to enable debug output
_TRACE = False

# regex used to recognize components of datetime strings
_str_datetime = r'\A(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)' \
    r'(T(?P<time>\d\d:\d\d:\d\d[-+\.Z\d:]*))?\Z'
_regex_datetime = re.compile(_str_datetime)

_regex_coding = re.compile(r'\Acode_coding_(?P<num>\d)_')

_KEY_END           = 'end'
_KEY_START         = 'start'

# names for a DSTU2 and DSTU3 bundles seen from various FHIR servers
#_BUNDLE2_NAMES = ['FhirBundleCursorStu2', 'FhirBundleCursorDstu2']
#_BUNDLE3_NAMES = ['FhirBundleCursorStu3', 'FhirBundleCursorDstu3']

_STR_RESOURCE_TYPE = 'resourceType'


###############################################################################
def enable_debug():

    global _TRACE
    _TRACE = True


###############################################################################
def _dump_dict(dict_obj, msg=None):
    """
    Print to stdout the key-value pairs for the given dict.
    """

    assert dict == type(dict_obj)

    if msg is not None:
        print(msg)
    for k,v in dict_obj.items():
        if k.endswith('div'):
            print('\t{0} => {1}...'.format(k, v[:16]))
        else:
            print('\t{0} => {1}'.format(k, v))

    
###############################################################################
def _convert_datetimes(flattened_obj):
    """
    Convert FHIR datetimes to python datetime objects. The input is a flattened
    JSON representation of a FHIR resource.
    """

    assert dict == type(flattened_obj)
    
    for k,v in flattened_obj.items():
        if str == type(v):
            match = _regex_datetime.match(v)
            if match:
                year  = int(match.group('year'))
                month = int(match.group('month'))
                day   = int(match.group('day'))
                time_str = match.group('time')

                if time_str is None:
                    datetime_obj = datetime(
                        year  = year,
                        month = month,
                        day   = day
                    )
                else:
                    json_time = time_finder.run(time_str)
                    time_list = json.loads(json_time)
                    assert 1 == len(time_list)
                    the_time = time_list[0]
                    time_obj = time_finder.TimeValue(**the_time)

                    us = 0
                    if time_obj.fractional_seconds is not None:
                        # convert to int and keep us resolution
                        frac_seconds = int(time_obj.fractional_seconds)
                        us = frac_seconds % 999999

                    # get correct sign for UTC offset
                    mult = 1
                    if time_obj.gmt_delta_sign is not None:
                        if '-' == time_obj.gmt_delta_sign:
                            mult = -1
                    delta_hours = 0
                    if time_obj.gmt_delta_hours is not None:
                        delta_hours = mult * time_obj.gmt_delta_hours
                    delta_min = 0
                    if time_obj.gmt_delta_minutes is not None:
                        delta_min   = time_obj.gmt_delta_minutes
                    offset = timedelta(
                        hours=delta_hours,
                        minutes = delta_min
                    )
                
                    datetime_obj = datetime(
                        year        = year,
                        month       = month,
                        day         = day,
                        hour        = time_obj.hours,
                        minute      = time_obj.minutes,
                        second      = time_obj.seconds,
                        microsecond = us,
                        tzinfo      = timezone(offset=offset)
                    )

                flattened_obj[k] = datetime_obj
                
    return flattened_obj


###############################################################################
def _set_list_length(obj, prefix_str):
    """
    Determine the length of a flattened list whose element keys share the
    given prefix string. Add a new key of the form 'len_' + prefix_str that
    contains this length.
    """

    str_search = r'\A' + prefix_str + r'_(?P<num>\d+)_?'
    
    max_num = None
    for k,v in obj.items():
        match = re.match(str_search, k)
        if match:
            num = int(match.group('num'))
            if max_num is None:
                max_num = 0
            if num > max_num:
                max_num = num

    if max_num is None:
        return 0
    else:
        length = max_num + 1
        obj['len_' + prefix_str] = length
        return length


###############################################################################
def _base_init(obj):
    """
    Initialize list lengths in the base resource objects.
    """

    identifier_count = _set_list_length(obj, 'identifier')
    for i in range(identifier_count):
        key_name = 'identifier_{0}_type_coding'.format(i)
        _set_list_length(obj, key_name)

    for field in ['extension', 'modifierExtension']:
        count = _set_list_length(obj, field)
        for i in range(count):
            key_name = '{0}_{1}_valueCodeableConcept_coding'.format(field, i)
            _set_list_length(obj, key_name)
            key_name = '{0}_{1}_valueTiming_event'.format(field, i)
            _set_list_length(obj, key_name)
            key_name = '{0}_{1}_valueTiming_code_coding'.format(field, i)
            _set_list_length(obj, key_name)
            key_name = '{0}_{1}_valueAddress_line'.format(field, i)
            _set_list_length(obj, key_name)
            for hn_field in ['family', 'given', 'prefix', 'suffix']:
                key_name = '{0}_{1}_valueHumanName_{2}'.format(field, i, hn_field)
                _set_list_length(obj, key_name)
            key_name = '{0}_{1}_valueSignature_type_coding'.format(field, i)
            _set_list_length(obj, key_name)
            # set lengths of inner extension lists
            key_name = '{0}_{1}_extension'.format(field, i)
            _set_list_length(obj, key_name)
        

###############################################################################        
def _contained_med_resource_init(obj):
    """
    Decode a flattened FHIR DSTU2 Medication resource. These appear only as
    contained resources in the CarePlan, Group, MedicationAdministration,
    MedicationDispense, MedicationOrder, MedicationStatement, Procedure,
    SupplyDelivery, and SupplyRequest resources.

    For more info see: http://hl7.org/fhir/DSTU2/medication.html.
    """

    contained_count = _set_list_length(obj, 'contained')
    for i in range(contained_count):
        for field in [
                'code_coding', 'product_form', 'product_ingredient',
                'product_batch', 'package_container_coding',
                'package_content']:
            key_name = 'contained_{0}_{1}'.format(i, field)
            _set_list_length(obj, key_name)
            
    
###############################################################################
def _decode_dstu2_observation(obj):
    """
    Decode a flattened FHIR 'Observation' resource.
    """

    assert dict == type(obj)

    if _TRACE:
        _dump_dict(obj, '[BEFORE]: Flattened Observation: ')
    
    # add 'date_time' field for time sorting
    KEY_EDT = 'effectiveDateTime'
    KEY_EP  = 'effectivePeriod'
    if KEY_EDT in obj:
        edt = obj[KEY_EDT]
        obj[KEY_DATE_TIME] = edt
    if KEY_EP in obj:
        if _KEY_START in obj[KEY_EP]:
            start = obj[KEY_EP][_KEY_START]
            obj[KEY_DATE_TIME] = start
        if _KEY_END in obj[KEY_EP]:
            end = obj[KEY_EP][_KEY_END]
            obj[KEY_END_DATE_TIME] = end

    _base_init(obj)
    _set_list_length(obj, 'category_coding')
    _set_list_length(obj, 'code_coding')
    _set_list_length(obj, 'performer')
    _set_list_length(obj, 'valueCodeableConcept_coding')
    _set_list_length(obj, 'dataAbsentReason_coding')
    _set_list_length(obj, 'interpretation_coding')
    _set_list_length(obj, 'bodySite_coding')
    _set_list_length(obj, 'method_coding')
    rr_count = _set_list_length(obj, 'referenceRange')
    for i in range(rr_count):
        key = 'referenceRange_{0}_meaning_coding'.format(i)
        _set_list_length(obj, key)
    component_count = _set_list_length(obj, 'component')
    for i in range(component_count):
        for field in ['code_coding',
                      'valueCodeableConcept_coding',
                      'dataAbsentReason_coding',
                      'referenceRange']:
            key = 'component_{0}_{1}'.format(i, field)
            _set_list_length(obj, key)

    # set value and units for result display
    KEY_VQ = 'valueQuantity_value'
    KEY_VU = 'valueQuantity_unit'
    KEY_DISP = 'code_coding_0_display'
    if KEY_VQ in obj:
        obj[KEY_VALUE] = obj[KEY_VQ]
    if KEY_VU in obj:
        obj[KEY_UNITS] = obj[KEY_VU]
    if KEY_DISP in obj:
        obj[KEY_VALUE_NAME] = obj[KEY_DISP]
        
    if _TRACE:
        _dump_dict(obj, '[AFTER] Flattened Observation: ')
            
    return obj


###############################################################################
def _decode_dstu2_medication_administration(obj):
    """
    Decode a flattened FHIR DSTU2 'MedicationAdministration' resource.
    """

    assert dict == type(obj)

    if _TRACE:
        _dump_dict(obj, '[BEFORE]: Flattened MedicationAdministration: ')
    
    # add fields for time sorting
    KEY_EDT = 'effectiveTimeDateTime'
    KEY_EP  = 'effectiveTimePeriod'
    if KEY_EDT in obj:
        edt = obj[KEY_EDT]
        obj[KEY_DATE_TIME] = edt
    if KEY_EP in obj:
        if _KEY_START in obj[KEY_EP]:
            start = obj[KEY_EP][_KEY_START]
            obj[KEY_DATE_TIME] = start
        if _KEY_END in obj[KEY_EP]:
            end = obj[KEY_EP][_KEY_END]
            obj[KEY_END_DATE_TIME] = end

    _base_init(obj)
    _contained_med_resource_init(obj)
    
    reason_count = _set_list_length(obj, 'reasonNotGiven')
    for i in range(reason_count):
        key = 'reasonNotGiven_{0}_coding'
        _set_list_length(obj, key)
    reason_count = _set_list_length(obj, 'reasonGiven')
    for i in range(reason_count):
        key = 'reasonGiven_{0}_coding'
        _set_list_length(obj, key)
    _set_list_length(obj, 'medicationCodeableConcept_coding')
    _set_list_length(obj, 'device')
    _set_list_length(obj, 'dosage_siteCodeableConcept_coding')
    _set_list_length(obj, 'dosage_route_coding')
    _set_list_length(obj, 'dosage_method_coding')

    # set data for result display
    KEY_DISP = 'medicationCodeableConcept_coding_0_display'
    if KEY_DISP in obj:
        obj[KEY_VALUE_NAME] = obj[KEY_DISP]
    else:
        KEY_REF = 'medicationReference_display'
        if KEY_REF in obj:
            obj[KEY_VALUE_NAME] = obj[KEY_REF]
    
    if _TRACE:
        _dump_dict(obj, '[AFTER]: Flattened MedicationAdministration: ')

    return obj
            
    
###############################################################################
def _decode_dstu2_medication_order(obj):
    """
    Decode a flattened FHIR DSTU2 'MedicationOrder' resource.
    """

    assert dict == type(obj)

    if _TRACE:
        _dump_dict(obj, '[BEFORE]: Flattened MedicationOrder: ')
    
    # add fields for time sorting
    KEY_DW = 'dateWritten'
    if KEY_DW in obj:
        dw = obj[KEY_DW]
        obj[KEY_DATE_TIME] = dw

    KEY_DE = 'dateEnded'
    if KEY_DE in obj:
        de = obj[KEY_DE]
        obj[KEY_END_DATE_TIME] = de

    _base_init(obj)
    _contained_med_resource_init(obj)
    
    _set_list_length(obj, 'reasonEnded_coding')
    _set_list_length(obj, 'reasonCodeableConcept_coding')
    _set_list_length(obj, 'medicationCodeableConcept_coding')
    inst_count = _set_list_length(obj, 'dosageInstruction')
    for i in range(inst_count):
        for field in ['additionalInstructions_coding',
                      'timing_code_coding',
                      'asNeededCodeableConcept_coding',
                      'siteCodeableConcept_coding',
                      'route_coding', 'method_coding']:
            key = 'dosageInstruction_{0}_{1}'.format(i, field)
            _set_list_length(obj, key)
    _set_list_length(obj, 'dispenseRequest_medicationCodeableConcept_coding')
    _set_list_length(obj, 'substitution_type_coding')
    _set_list_length(obj, 'substitution_reason_coding')

    # set data for result display
    KEY_DISP = 'medicationCodeableConcept_coding_0_display'
    if KEY_DISP in obj:
        obj[KEY_VALUE_NAME] = obj[KEY_DISP]
    else:
        KEY_REF = 'medicationReference_display'
        if KEY_REF in obj:
            obj[KEY_VALUE_NAME] = obj[KEY_REF]
    
    if _TRACE:
        _dump_dict(obj, '[AFTER]: Flattened MedicationOrder: ')

    return obj
                

###############################################################################
def _decode_dstu2_medication_statement(obj):
    """
    Decode a flattened FHIR DSTU2 'MedicationStatement' resource.
    """

    assert dict == type(obj)

    if _TRACE:
        _dump_dict(obj, '[BEFORE]: Flattened Medication Statement: ')    

    # add fields for time sorting
    KEY_DA = 'dateAsserted'
    if KEY_DA in obj:
        da = obj[KEY_DA]
        obj[KEY_DATE_TIME] = da
    
    _base_init(obj)
    _contained_med_resource_init(obj)
    
    reason_count = _set_list_length(obj, 'reasonNotTaken')
    for i in range(reason_count):
        key = 'reason_{0}_coding'
        _set_list_length(obj, key)
    _set_list_length(obj, 'reasonForUseCodeableConcept_coding')
    _set_list_length(obj, 'supportingInformation')
    _set_list_length(obj, 'medicationCodeableConcept_coding')
    dosage_count = _set_list_length(obj, 'dosage')
    for i in range(dosage_count):
        for field in ['asNeededCodeableConcept_coding',
                      'siteCodeableConcept_coding',
                      'route_coding', 'method_coding']:
            key = 'dosage_{0}_{1}'.format(i, field)
            _set_list_length(obj, key)

    # set data for result display
    KEY_DISP = 'medicationCodeableConcept_coding_0_display'
    if KEY_DISP in obj:
        obj[KEY_VALUE_NAME] = obj[KEY_DISP]
    else:
        KEY_REF = 'medicationReference_display'
        if KEY_REF in obj:
            obj[KEY_VALUE_NAME] = obj[KEY_REF]

    if _TRACE:
        _dump_dict(obj, '[AFTER]: Flattened Medication Statement: ')

    return obj


###############################################################################
def _decode_dstu2_condition(obj):
    """
    Decode a flattened FHIR DSTU2 'Condition' resource.
    """

    assert dict == type(obj)

    if _TRACE:
        _dump_dict(obj, '[BEFORE]: Flattened Condition: ')    

    KEY_ODT = 'onsetDateTime'
    KEY_OP  = 'onsetPeriod'
    KEY_ADT = 'abatementDateTime'
    KEY_AP  = 'abatementPeriod'

    # add fields for time sorting
    if KEY_ODT in obj:
        odt = obj[KEY_ODT]
        obj[KEY_DATE_TIME] = odt
    if KEY_ADT in obj:
        adt = obj[KEY_ADT]
        obj[KEY_END_DATE_TIME] = adt

    if KEY_OP in obj:
        start = obj[KEY_OP][_KEY_START]
        obj[KEY_DATE_TIME] = start
    if KEY_AP in obj:
        end = obj[KEY_AP][_KEY_END]
        obj[KEY_END_DATE_TIME] = end
    
    _base_init(obj)
    _set_list_length(obj, 'code_coding')
    _set_list_length(obj, 'category_coding')
    _set_list_length(obj, 'severity_coding')
    _set_list_length(obj, 'stage_assessment')
    evidence_len = _set_list_length(obj, 'evidence')
    for i in range(evidence_len):
        for field in ['code_coding', 'detail']:
            key = 'evidence_{0}_{1}'.format(i, field)
            _set_list_length(obj, key)
    site_count = _set_list_length(obj, 'bodySite')
    for i in range(site_count):
        key_name = 'bodySite_{0}_coding'.format(i)
        _set_list_length(obj, key_name)

    # set data for result display
    KEY_DISP = 'code_coding_0_display'
    if KEY_DISP in obj:
        obj[KEY_VALUE_NAME] = obj[KEY_DISP]
        
    if _TRACE:
        _dump_dict(obj, '[AFTER]: Flattened Condition: ')

    return obj
    

###############################################################################
def _decode_dstu2_procedure(obj):
    """
    Decode a flattened FHIR DSTU2 'Procedure' resource.
    """

    assert dict == type(obj)

    if _TRACE:
        _dump_dict(obj, '[BEFORE]: Flattened Procedure: ')

    # add fields for time sorting
    KEY_PDT = 'performedDateTime'
    KEY_PP  = 'performedPeriod'
    if KEY_PDT in obj:
        # only a single timestamp
        pdt = obj[KEY_PDT]
        obj[KEY_DATE_TIME] = pdt
    if KEY_PP in obj:
        # period, one or both timestamps could be present
        if _KEY_START in obj[KEY_PP]:
            start = obj[KEY_PP][_KEY_START]
            obj[KEY_DATE_TIME] = start
        if _KEY_END in obj[KEY_PP]:
            end = obj[KEY_PP][_KEY_END]
            obj[KEY_END_DATE_TIME] = end
    
    _base_init(obj)
    _contained_med_resource_init(obj)

    _set_list_length(obj, 'category_coding')
    _set_list_length(obj, 'code_coding')
    _set_list_length(obj, 'reasonNotPerformed_coding')
    site_count = _set_list_length(obj, 'bodySite')
    for i in range(site_count):
        key_name = 'bodySite_{0}_coding'.format(i)
        _set_list_length(obj, key_name)
    _set_list_length(obj, 'reasonCodeableConcept_coding')
    performer_count = _set_list_length(obj, 'performer')
    for i in range(performer_count):
        key_name = 'performer_{0}_role_coding'.format(i)
        _set_list_length(obj, key_name)
    _set_list_length(obj, 'outcome_coding')
    _set_list_length(obj, 'report')
    complication_count = _set_list_length(obj, 'complication')
    for i in range(complication_count):
        key_name = 'complication_{0}_coding'.format(i)
        _set_list_length(obj, key_name)
    followup_count = _set_list_length(obj, 'followUp')
    for i in range(followup_count):
        key_name = 'followUp_{0}_coding'.format(i)
        _set_list_length(obj, key_name)
    _set_list_length(obj, 'notes')
    device_count = _set_list_length(obj, 'focalDevice')
    for i in range(device_count):
        key_name = 'focalDevice_{0}_action_coding'.format(i)
        _set_list_length(obj, key_name)
    _set_list_length(obj, 'used')

    # set data for result display
    KEY_DISP = 'code_coding_0_display'
    if KEY_DISP in obj:
        obj[KEY_VALUE_NAME] = obj[KEY_DISP]
    
    if _TRACE:
        _dump_dict(obj, '[AFTER]: Flattened Procedure: ')

    return obj
    

###############################################################################
def _decode_dstu2_patient(obj):
    """
    Flatten and decode a FHIR DSTU2 'Patient' resource.
    """

    obj_type = type(obj)
    if str == obj_type:
        # not flattened yet

        try:
            obj = json.loads(obj)
        except json.decoder.JSONDecoderError as e:
            print('\t{0}: String conversion (patient) failed with error: "{1}"'.
                  format(_MODULE_NAME, e))
            return result

        # the type instantiated from the string should be a dict
        obj_type = type(obj)
        
    assert dict == obj_type

    flattened_patient = flatten(obj)
    flattened_patient = _convert_datetimes(flattened_patient)

    if _TRACE:
        _dump_dict(flattened_patient, '[BEFORE] Flattened Patient resource: ')
    
    _base_init(flattened_patient)

    name_count = _set_list_length(flattened_patient, 'name')
    for i in range(name_count):
        for field in ['family', 'given', 'prefix', 'suffix']:
            key_name = 'name_{0}_{1}'.format(i, field)
            count = _set_list_length(flattened_patient, key_name)
            for j in range(count):
                key = '{0}_{1}'.format(key_name, j)
                _set_list_length(flattened_patient, key)

    _set_list_length(flattened_patient, 'telecom')
    addr_count = _set_list_length(flattened_patient, 'address')
    for i in range(addr_count):
        key_name = 'address_{0}_line'.format(i)
        _set_list_length(flattened_patient, key_name)

    _set_list_length(flattened_patient, 'maritalStatus_coding')
    
    contact_count = _set_list_length(flattened_patient, 'contact')
    for i in range(contact_count):
        for field in ['relationship', 'telecom']:
            key_name = 'contact_{0}_{1}'.format(i, field)
            count = _set_list_length(flattened_patient, key_name)
            for j in range(count):
                key = '{0}_{1}_coding'.format(key_name, j)
                _set_list_length(flattened_patient, key)

    _set_list_length(flattened_patient, 'animal_species_coding')
    _set_list_length(flattened_patient, 'animal_breed_coding')
    _set_list_length(flattened_patient, 'animal_genderStatus_coding')    

    comm_count = _set_list_length(flattened_patient, 'communication')
    for i in range(comm_count):
        key_name = 'communication_{0}_language_coding'.format(i)
        _set_list_length(flattened_patient, key_name)

    _set_list_length(flattened_patient, 'careProvider')
    _set_list_length(flattened_patient, 'link')

    # set data for result display
    family = ''
    if 'name_0_family' in flattened_patient:
        family = flattened_patient['name_0_family']
    elif 'name_0_family_0' in flattened_patient:
        family = flattened_patient['name_0_family_0']
    given = ''
    if 'name_0_given' in flattened_patient:
        given = flattened_patient['name_0_given']
    elif 'name_0_given_0' in flattened_patient:
        given = flattened_patient['name_0_given_0']
    name = '{0}, {1}'.format(family, given)
    flattened_patient[KEY_VALUE_NAME] = name
    
    if _TRACE:
        _dump_dict(flattened_patient, '[AFTER] Flattened Patient resource: ')

    return flattened_patient


###############################################################################
def _process_dstu2_resource(obj):
    """
    Flatten and decode a FHIR DSTU2 resource.
    """

    obj_type = type(obj)
    assert dict == obj_type

    # flatten the JSON, convert time strings to datetimes
    flattened_obj = flatten(obj)
    flattened_obj = _convert_datetimes(flattened_obj)

    # read the resource type and process accordingly
    result = None
    if _STR_RESOURCE_TYPE in flattened_obj:
        rt = obj[_STR_RESOURCE_TYPE]
        if 'Patient' == rt:
            result = _decode_dstu2_patient(flattened_obj)
        elif 'Observation' == rt:
            result = _decode_dstu2_observation(flattened_obj)
        elif 'Procedure' == rt:
            result = _decode_dstu2_procedure(flattened_obj)
        elif 'Condition' == rt:
            result = _decode_dstu2_condition(flattened_obj)
        elif 'MedicationStatement' == rt:
            result = _decode_dstu2_medication_statement(flattened_obj)
        elif 'MedicationOrder' == rt:
            result = _decode_dstu2_medication_order(flattened_obj)
        elif 'MedicationAdministration' == rt:
            result = _decode_dstu2_medication_administration(flattened_obj)

    return result
    

###############################################################################
def _decode_bundle(name, bundle_obj, result_type_str):
    """
    Decode a CQL Engine bundle object.
    """

    if _TRACE: print('Decoding BUNDLE resource...')

    # this bundle should be a string representation of a list of dicts
    obj_type = type(bundle_obj)
    assert str == obj_type
    
    try:
        obj = json.loads(bundle_obj)
    except json.decoder.JSONDecodeError as e:
        print('\t{0}: String conversion (bundle) failed with error: "{1}"'.
              format(_MODULE_NAME, e))
        return []

    # now find out what type of obj was created from the string
    obj_type = type(obj)
    assert list == obj_type

    rts = result_type_str.lower()
    
    bundled_objs = []    
    for elt in obj:
        if rts.endswith('stu2'):
            result = _process_dstu2_resource(elt)
        elif rts.endswith('stu3'):
            # process via the DSTU2 route for now...
            result = _process_dstu2_resource(elt)
        if result is not None:
            bundled_objs.append(result)
    
    return bundled_objs


###############################################################################
def decode_top_level_obj(obj):
    """
    Decode the outermost object type returned by the CQL Engine.
    """

    KEY_NAME        = 'name'
    KEY_RESULT      = 'result'
    KEY_RESULT_TYPE = 'resultType'
    STR_PATIENT     = 'patient'
    
    result_obj = None
    
    obj_type = type(obj)
    if dict == obj_type:
        if _TRACE: print('top_level_obj dict keys: {0}'.format(obj.keys()))

        name = None
        if KEY_NAME in obj:
            name = obj[KEY_NAME]
        if KEY_RESULT_TYPE in obj and KEY_RESULT in obj:
            result_obj = obj[KEY_RESULT]
            result_type_str = obj[KEY_RESULT_TYPE].lower()
            
            if STR_PATIENT == result_type_str:
                result_obj = _decode_dstu2_patient(result_obj)
                if _TRACE: print('decoded patient')
            else:
                # check for DSTU2 or DSTU3 resource bundles
                if result_type_str.endswith('stu2') or result_type_str.endswith('stu3'):    
                    result_obj = _decode_bundle(name, result_obj, result_type_str)
                else:
                    if _TRACE: print('no decode')
                    result_obj = None
    else:
        # don't know what else to expect here
        assert False

    return result_obj


###############################################################################
def _get_version():
    return '{0} {1}.{2}'.format(_MODULE_NAME, _VERSION_MAJOR, _VERSION_MINOR)


###############################################################################
if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Decode Cerner DSTU2 FHIR resource examples')

    parser.add_argument('-v', '--version',
                        action='store_true',
                        help='show the version string and exit')
    parser.add_argument('-f', '--filepath',
                        help='path to JSON file containing CQL Engine results')
    parser.add_argument('-d', '--debug',
                        action='store_true',
                        help='print debug info to stdout')

    args = parser.parse_args()

    if 'version' in args and args.version:
        print(_get_version())
        sys.exit(0)

    if 'debug' in args and args.debug:
        enable_debug()

    filepath = None
    if 'filepath' in args and args.filepath:
        filepath = args.filepath
        if not os.path.isfile(filepath):
            print('Unknown file specified: "{0}"'.format(filepath))
            sys.exit(-1)
    
    with open(filepath, 'rt') as infile:
        json_string = infile.read()
        json_data = json.loads(json_string)

        result = _process_dstu2_resource(json_data)

        print('RESULT: ')
        if result is not None:
            for k,v in result.items():
                if dict == type(v):
                    print('\t{0}'.format(k))
                    for k2,v2 in v.items():
                        print('\t\t{0} => {1}'.format(k2, v2))
                elif list == type(v):
                    print('\t{0}'.format(k))
                    for index, v2 in enumerate(v):
                        print('\t\t[{0}]:\t{1}'.format(index, v2))
                else:
                    print('\t{0} => {1}'.format(k,v))
