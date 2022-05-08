#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from argparse import ArgumentParser
import csv
import os
import json
import re
import logging

def read_lines(txt_file):
    with open(txt_file, newline='') as txtfile:
        return [line.rstrip() for line in txtfile.readlines()]

def read_json(json_file):
    with open(json_file) as json_file:
        data = json.load(json_file)
        return data

def read_csv(csv_file):
    with open(csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        fields = list(reader)
        return fields

def load_data(surface_forms_file, ref_file, sys_file):
    surface_forms = read_json(surface_forms_file)

    ref_file_ext = os.path.splitext(ref_file)[1]
    if ref_file_ext == ".csv":
        ref = read_csv(ref_file)
    elif ref_file_ext == ".json":
        ref = read_json(ref_file)

    das = [row["da"] for row in ref]

    if sys_file:
        sys = read_lines(sys_file)
    else:
        sys = [row["text"] for row in ref]

    assert len(das) == len(sys), f"Number of references and system outputs must match ({len(das)} != {len(sys)})"
    return surface_forms, das, sys

def parse_da(da):
    '''
    Parses one line of Dialogue Act in the form of "DA_TYPE(SLOT=VALUE,...)".
    '''

    # Each DA string has exactly one set of parentheses,
    # they contain the attributes of the da_type (or contain nothing)
    da_type, attributes_string = da[:-1].split("(")
    
    if attributes_string != "":
        # Commas separate the attributes, no attribute value contain the comma inside the string
        splitted_attributes = attributes_string.split(",")
    else:
        # We have DAs that do not contain any attributes
        splitted_attributes = []
    
    # We store the attributes inside dictionary, slots are unordered.
    # For some DAs the slots repeat 2 times, we therefore store 
    # two values for these cases and keep the slots as unique keys
    parsed_attributes = {}
    for attr_string in splitted_attributes:
        # Start with parsing the splitted attributes string

        # Separated attributes contain either a slot constant or a slot with one value.
        # Slot and its value are separated by "="
        split_attr = attr_string.split("=")
        slot = split_attr[0]
        num_values = len(split_attr) - 1
        if num_values == 0:
            parsed_attributes[slot] = []
        elif num_values == 1:
            value = split_attr[1]
            # value may contain apostrophes around the string
            # it never contains more than these two.
            value = value.replace("'", "")

            # the value string may contain two actual values separated by " or "
            if " or " in value:
                parsed_attributes[slot] = value.split(" or ")
            else:
                # if the slot already exists, we add the new value
                if slot in parsed_attributes:
                    parsed_attributes[slot].append(value)
                else:
                    parsed_attributes[slot] = [value]

    return {
        "type": da_type,
        "attributes": parsed_attributes
    }

def test_parse_da():
    da = "inform(abc=123)"
    parsed = parse_da(da)
    
    assert parsed == {
        "type": "inform",
        "attributes": {"abc" : ["123"]}
    }
    da = "inform()"
    parsed = parse_da(da)
    assert parsed == {
        "type": "inform",
        "attributes": {}
    }
    da = "?request(rr='Baráčnická Rychta',rr=dont_care,cc=382)"
    parsed = parse_da(da)
    assert parsed == {
        "type": "?request",
        "attributes": {"rr": ["Baráčnická Rychta", "dont_care"], "cc": ["382"]}
    }
test_parse_da()

def evaluate(surface_forms, das, sys):
    def exact_match(sentence, value):
        value = str(value)
        if value in sentence:
            return value
        else:
            return False
    
    def regex_match(sentence, regex, group=0):
        matches = re.search(regex, sentence, re.IGNORECASE)
        if matches:
            return matches.group(group)
        else:
            return False

    def address_match(street_value, sentence, forms):
        street_name, street_num = street_value.rsplit(" ", 1)
        if street_name in forms:
            for test_name in forms[street_name]:
                test_address = f"{test_name} {street_num}"
                if test_address in sentence:
                    return test_address
        return False

    def surface_forms_match(sentence, forms):
        # We look for some variations in capitalization
        capitalized_first_letters = [form.title() for form in forms]
        forms = set(forms + capitalized_first_letters)
        # We try to match the longest subsequences first
        forms = sorted(forms, key=len, reverse=True)

        for form in forms:
            i = sentence.find(form)
            if i >= 0:
                return sentence[i:i+len(form)]
            else:
                # Try to find the form in uncapitalized sentence
                uncapitalized_sentence = sentence[0].lower() + sentence[1:]
                j = uncapitalized_sentence.find(form)
                if j >= 0:
                    return sentence[j:j+len(form)]

        return False

    def remove_from_sentence(sentence, value):
        if value:
            new_sentence = "".join(sentence.split(value))
            # Replace multiple spaces with one
            new_sentence = re.sub(' +',' ',new_sentence)
            assert new_sentence != sentence, f"didn't find match for value {value} in sentence {sentence}"
            return new_sentence
        else:
            return sentence
    
    def find_kids_negation(sys_line):
        match = regex_match(sys_line, r"\b(ne\w*) (?:\w+ ){0,4}dět\w*", group=1)
        if not match:
            # (?!a ) is there because of "... a ..." conjunction
            match = regex_match(sys_line, r"dět\w* (?!a )(?:\w+ ){0,2}(ne\w+)", group=1)
        if not match:
            match = regex_match(sys_line, r"(zakáz\w*|zákaz\w*) (?:\w+ ){0,5}dět\w*", group=1)
        if not match:
            match = regex_match(sys_line, r"dět\w* (?:\w+ ){0,5}(zakáz\w*|zákaz\w*)", group=1)
        if not match:
            match = regex_match(sys_line, r"(bez) (?:\w+ ){0,3}dět\w*", group=1)
        return match
    
    def count_slot_missing_error(is_valid):
        nonlocal num_valid_slot_values, num_missing_slot_value_error
        num_valid_slot_values += 1
        if not is_valid:
            num_missing_slot_value_error += 1
    
    def log_slot_missing_error(is_valid, value, slot, sys_line):
        if not is_valid:
            logging.info(f"Slot Error: didn't find match for '{value}' for slot '{slot}' in sentence '{sys_line}'")
    
    def log_additional_slot_error(substring, slot, sys_line, da_line):
        logging.info(f"Slot Error: found substring '{substring}' implying slot '{slot}' in sentence '{sys_line}'. DA is '{da_line}'")


    surface_forms = {slot: {lemma: [form.split("\t")[1] for form in forms] for lemma, forms in values.items()} for slot, values in surface_forms.items()}
    num_cannot_check_slot_values = 0
    num_total_num_of_slot_values = 0
    num_type_slots = 0

    num_valid_slot_values = 0
    num_missing_slot_value_error = 0
    num_additional_slot_value_error = 0

    for da_line, sys_line_orig in list(zip(das, sys)):
        sys_line = sys_line_orig
        da = parse_da(da_line)
        attributes = da["attributes"]

        num_total_num_of_slot_values += sum(len(values) for _, values in attributes.items())
        # we count the empty slots as one value
        num_total_num_of_slot_values += sum(len(values) == 0 for _, values in attributes.items())

        attribute_priorities = {
            "kids_allowed": 10
        }
        attribute_list = [(slot, values, attribute_priorities[slot] if slot in attribute_priorities else 99) for slot, values in attributes.items()]
        attribute_list = sorted(attribute_list, key=lambda x: x[2])
        for slot, values, _ in attribute_list:
            # We cannot handle slots with no values, we log the number of these unhandled cases
            # The only slot that we can handle with no value is the kids_allowed
            if slot != "kids_allowed" and values == []:
                # we count missing values as one slot value
                num_cannot_check_slot_values += 1
                logging.debug(f"Coverage problem: We cannot handle {slot} with no value.")
                continue
            
            # Big switch statement for handling different slot types
            if slot == "type":
                num_type_slots += 1
                num_cannot_check_slot_values += 1
                # We don't log the coverage problem here because we don't have to check this slot
                continue
            elif slot == "kids_allowed":

                match_kids_slot = surface_forms_match(sys_line, ["děti", "dětí", "dětem", "dětmi"])

                # For two examples in the train set the value is missing but =yes is assumed
                if len(values) == 0:
                    values = ["yes"]

                if len(values) == 1:
                    value = values[0]
                    if value == "yes":
                        match_kids_negation = find_kids_negation(sys_line)
                        # the sentence needs to contain the word kids
                        # but cannot contain negation before/after kids
                        is_valid = match_kids_slot and not match_kids_negation
                        count_slot_missing_error(is_valid)
                        log_slot_missing_error(is_valid, value, slot, sys_line_orig)
                    elif value == "no":
                        match_kids_negation = find_kids_negation(sys_line)
                        # the sentence needs to contain the word kids
                        # and must contain negation before/after kids
                        is_valid = match_kids_slot and match_kids_negation
                        count_slot_missing_error(is_valid)
                        sys_line = remove_from_sentence(sys_line, match_kids_negation)
                        log_slot_missing_error(is_valid, value, slot, sys_line_orig)
                    elif value == "dont_care":
                        num_cannot_check_slot_values += 1
                        logging.debug(f"Coverage problem: We cannot handle kids_allowed='dont_care'")
                    elif value == "none":
                        num_cannot_check_slot_values += 1
                        logging.debug(f"Coverage problem: We cannot handle kids_allowed='none'")
                    else:
                        assert False, f"Invalid value {value} for kids_allowed"

                if len(values) == 2:
                    if set(values) == {"yes", "no"}:
                        num_cannot_check_slot_values += 2
                        logging.debug(f"Coverage problem: We cannot handle kids_allowed='yes or no'")
                    elif set(values) == {"dont_care", "yes"}:
                        num_cannot_check_slot_values += 2
                        logging.debug(f"Coverage problem: We cannot handle kids_allowed='yes',kids_allowed='dont_care'")
                    else:
                        assert False, f"Invalid value {values} for kids_allowed"
                
                # Warning, this is maybe dangerous - but we remove all matched "děti" string
                while match_kids_slot:
                    sys_line = remove_from_sentence(sys_line, match_kids_slot)
                    match_kids_slot = surface_forms_match(sys_line, ["děti", "dětí", "dětem", "dětmi"])
                # This is because we don't want to trigger the "additional slot" error 
                # for the slot values we cannot handle

            elif slot in ["phone", "count", "postcode"]:
                # TODO: For count we might want to implement checking numerals (such as "dvě", "tři", ...)
                for value in values:
                    match = exact_match(sys_line, value)
                    count_slot_missing_error(match)
                    sys_line = remove_from_sentence(sys_line, match)
                    log_slot_missing_error(match, value, slot, sys_line_orig)
            elif slot == "address":
                for value in values:
                    match = address_match(value, sys_line, surface_forms["street"])
                    count_slot_missing_error(match)
                    sys_line = remove_from_sentence(sys_line, match)
                    log_slot_missing_error(match, value, slot, sys_line_orig)
            elif slot == "price":
                for value in values:
                    if "between" in value:
                        # remove text around prices
                        value = value[8:-3]
                        price1, price2 = value.split(" and ")
                        match = False
                        for form in surface_forms["price"]["between _ and _ Kč"]:
                            form = form.split("_")
                            assert len(form) == 3
                            czech_between_string = form[0] + price1 + form[1] + price2 + form[2]
                            match = exact_match(sys_line, czech_between_string)
                            if match:
                                break
                    else:
                        match = exact_match(sys_line, value)
                    
                    count_slot_missing_error(match)
                    sys_line = remove_from_sentence(sys_line, match)
                    log_slot_missing_error(match, value, slot, sys_line_orig)
            elif slot in surface_forms:
                for value in values:
                    if value in surface_forms[slot]:
                        match = surface_forms_match(sys_line, surface_forms[slot][value])
                        count_slot_missing_error(match)
                        sys_line = remove_from_sentence(sys_line, match)
                        log_slot_missing_error(match, value, slot, sys_line_orig)
                    else:
                        # TODO: handle dont_care
                        if value == "dont_care":
                            num_cannot_check_slot_values += 1
                            logging.debug(f"Coverage problem: We cannot handle value 'dont_care' for slot {slot}")
                        # TODO: handle none
                        if value == "none":
                            num_cannot_check_slot_values += 1
                            logging.debug(f"Coverage problem: We cannot handle value 'none' for slot {slot}")
            else:
                logging.error(f"Invalid slot in the parsed attributes of DA '{da_line}': {slot}")
                pass
        
        
        # Find additional slot values that are not supposed to be in the system output
        for surface_forms_slot in surface_forms:

            # Do not check those slots that are inside the DA without any value
            # These often list some or all of the value keywords to raise a question to the user
            if surface_forms_slot in attributes and attributes[surface_forms_slot] == []:
                continue

            if surface_forms_slot == "price_range":
                continue
            for forms in surface_forms[surface_forms_slot].values():
                match = surface_forms_match(sys_line, forms)
                if match:
                    log_additional_slot_error(match, surface_forms_slot, sys_line_orig, da_line)
                    num_additional_slot_value_error += 1
                    # print(sys_line, forms)

        # Find additional kids_allowed slot
        match_kids_slot = surface_forms_match(sys_line, ["děti", "dětí", "dětem", "dětmi"])
        if match_kids_slot:
            log_additional_slot_error(match_kids_slot, "kids_allowed", sys_line_orig, da_line)
            num_additional_slot_value_error += 1

    logging.info(f"Total number of DAs: {len(das)}")

    diff_cannot_check = num_total_num_of_slot_values-num_valid_slot_values
    assert num_cannot_check_slot_values == diff_cannot_check, "The number of slots we know we cannot check should equal the total number of slots and the number of slots that we correctly handled"

    logging.info(f"Total number of slots: {num_total_num_of_slot_values}")
    logging.info(f"Slots that we cannot check: {num_cannot_check_slot_values}, out of which {num_type_slots} are 'type=restaurant' slots")
    errors = num_missing_slot_value_error+num_additional_slot_value_error
    print("Missing Slot Errors: ", num_missing_slot_value_error)
    print("Additional Slot Errors: ", num_additional_slot_value_error)
    print("Total Slot Errors: ", errors)
    print("Number of slots checked: ", num_valid_slot_values)
    if num_valid_slot_values:
        SER = errors / num_valid_slot_values
    else:
        logging.warning(f"Didn't find any valid slots")
        SER = 0

    print("SER:", SER)


if __name__ == '__main__':
    

    ap = ArgumentParser(description='Slot Error Rate evaluation for Czech restaurant information dataset')
    ap.add_argument('surface_forms_file', type=str, help='JSON file containing the surface forms for all slot values.')
    ap.add_argument('ref_file', type=str, help='References CSV file containing the dialogue acts (DAs) in the first column.')
    ap.add_argument('--sys_file', type=str, help='System output file to evaluate (text file with one output per line).')
    ap.add_argument('-v', '--verbosity', action="count", help="increase output verbosity (e.g., -vv is more than -v)")
    args = ap.parse_args()

    if args.verbosity == 3:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.verbosity == 2:
        logging.getLogger().setLevel(logging.INFO)
    if args.verbosity == 1:
        logging.getLogger().setLevel(logging.WARNING)
    if args.verbosity == 0:
        logging.getLogger().setLevel(logging.ERROR)

    surface_forms, das, sys = load_data(args.surface_forms_file, args.ref_file, args.sys_file)

    evaluate(surface_forms, das, sys)