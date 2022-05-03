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

    assert len(sys) == len(das), "Number of references and system outputs must match"
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
    def capitalize_first_letters(name_list):
        return [name.title() for name in name_list]

    def find_surface_form(sentence, forms):
        # We look for some variations in capitalization
        forms = set(forms + capitalize_first_letters(forms))
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

    def exact_match(sentence, value):
        value = str(value)
        if value in sentence:
            return value
        else:
            return False
    
    def regex_match(sentence, regex):
        matches = re.search(regex, sentence, re.IGNORECASE)
        if matches:
            return matches.group(0)
        else:
            return False
    
    def remove_from_sentence(sentence, value):
        new_sentence = "".join(sentence.split(value))
        # Replace multiple spaces with one
        new_sentence = re.sub(' +',' ',new_sentence)
        assert new_sentence != sentence, f"didn't find match for value {value} in sentence {sentence}"
        return new_sentence
    
    def match_address(street_value, sentence, forms):
        street_name, street_num = street_value.rsplit(" ", 1)
        if street_name in forms:
            for test_name in forms[street_name]:
                test_address = f"{test_name} {street_num}"
                if test_address in sentence:
                    return test_address
        return False
    
    # def find_kids_negation(sys_line):
    #     match = regex_match(sys_line, r"\bne\w* (\w+ ){0,5}dět\w*")
    #     if not match:
    #         match = regex_match(sys_line, r"dět\w* (\w+ ){0,2}ne\w+")
    #     if not match:
    #         match = regex_match(sys_line, r"(zakáz\w*|zákaz\w*) (\w+ ){0,5}dět\w*")
    #     if not match:
    #         match = regex_match(sys_line, r"dět\w* (\w+ ){0,5}(zakáz\w*|zákaz\w*)")
    #     if not match:
    #         match = regex_match(sys_line, r"bez (\w+ ){0,3}dět\w*")
    #     return match
    
    def validate_slot_match(sys_line, sys_line_orig, match, value, slot, num_valid_slots_with_value, num_missing_slot_value_error):
        num_valid_slots_with_value += 1
        if match:
            sys_line = remove_from_sentence(sys_line, match)
        else:
            num_missing_slot_value_error += 1
            logging.info(f"Slot Error: didn't find match for '{value}' for slot '{slot}' in sentence '{sys_line_orig}'")

        return sys_line, num_valid_slots_with_value, num_missing_slot_value_error

    surface_forms = {slot: {lemma: [form.split("\t")[1] for form in forms] for lemma, forms in values.items()} for slot, values in surface_forms.items()}
    # print(surface_forms)
    problems = 0
    num_valid_slots_with_value = 0
    num_missing_slot_value_error = 0
    num_additional_slot_value_error = 0

    for da_string, sys_line_orig in list(zip(das, sys)):
        sys_line = sys_line_orig
        da = parse_da(da_string)
        attributes = da["attributes"]

        # if "kids_allowed" in attributes:
        #     pass
        #     # logging.debug(f"{da_string} -> {sys_line}")
        # else:
        #     continue

        # num_slots_with_value = sum(1 if value else 0 for _, value in da["attributes"].items())

        # Find the slots that are supposed to be in the system output
        attribute_priorities = {
            "kids_allowed": 10
        }
        attribute_list = [(slot, values, attribute_priorities[slot] if slot in attribute_priorities else 99) for slot, values in attributes.items()]
        attribute_list = sorted(attribute_list, key=lambda x: x[2])
        for slot, values, _ in attribute_list:
            if slot == "type":
                continue
            elif slot == "kids_allowed":
                logging.debug(f"We cannot handle the slot kids_allowed yet")
                continue
                # num_valid_slots_with_value += 1

                # # the sentence needs to contain the word kids
                # match_kids_slot = find_surface_form(sys_line, ["děti", "dětí", "dětem", "dětmi"])
                # if not match_kids_slot:
                #     num_missing_slot_value_error += 1
                #     logging.info(f"Slot Error: didn't find match for 'děti' for slot '{slot}' in sentence '{sys_line_orig}'")
                #     continue

                # # For two examples in the train set the value is missing but =yes is assumed
                # if len(values) == 0:
                #     values = ["yes"]

                # if len(values) == 1:
                #     value = values[0]
                #     if value == "yes":
                #         match = find_kids_negation(sys_line)
                #         if match:
                #             logging.debug(f"!!! '{match}'\t'{sys_line}'\t{da_string}")
                #     elif value == "no":
                #         match = find_kids_negation(sys_line)
                #         if not match:
                #             logging.debug(f"'{match}'\t'{sys_line}'\t{da_string}")
                #     elif value == "dont_care":
                #         logging.debug(f"We cannot handle kids_allowed='dont_care' yet")
                #     elif value == "none":
                #         logging.debug(f"We cannot handle kids_allowed='none' yet")
                #     else:
                #         assert False, f"Invalid value {value} for kids_allowed"

                # if len(values) == 2:
                #     if set(values) == {"yes", "no"}:
                #         logging.debug(f"We cannot handle kids_allowed='yes or no' yet")
                #     elif set(values) == {"dont_care", "yes"}:
                #         logging.debug(f"We cannot handle kids_allowed='yes or no' yet")
                #     else:
                #         assert False, f"Invalid value {values} for kids_allowed"
            elif slot in ["phone", "count", "postcode"]:
                for value in values:
                    match = exact_match(sys_line, value)
                    sys_line, num_valid_slots_with_value, num_missing_slot_value_error = validate_slot_match(sys_line, sys_line_orig, match, value, slot, num_valid_slots_with_value, num_missing_slot_value_error)
            elif slot == "address":
                for value in values:
                    match = match_address(value, sys_line, surface_forms["street"])
                    sys_line, num_valid_slots_with_value, num_missing_slot_value_error = validate_slot_match(sys_line, sys_line_orig, match, value, slot, num_valid_slots_with_value, num_missing_slot_value_error)
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
                    
                    sys_line, num_valid_slots_with_value, num_missing_slot_value_error = validate_slot_match(sys_line, sys_line_orig, match, value, slot, num_valid_slots_with_value, num_missing_slot_value_error)
            elif slot in surface_forms:
                for value in values:
                    if value in surface_forms[slot]:
                        match = find_surface_form(sys_line, surface_forms[slot][value])
                        sys_line, num_valid_slots_with_value, num_missing_slot_value_error = validate_slot_match(sys_line, sys_line_orig, match, value, slot, num_valid_slots_with_value, num_missing_slot_value_error)
                    else:
                        # TODO: handle dont_care
                        # if value == "dont_care":
                        #     problems += 1
                        #     continue
                        #
                        logging.debug(f"Coverage problem: non-existing value '{value}' for slot {slot}")
            else:
                logging.error(f"Invalid slot in the parsed attributes of DA '{da_string}': {slot}")
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
                match = find_surface_form(sys_line, forms)
                if match:
                    logging.info(f"Slot Error: found additional value '{match}' for slot '{surface_forms_slot}' in sentence '{sys_line_orig}'. DA is '{da_string}'")
                    num_additional_slot_value_error += 1
                    # print(sys_line, forms)

        # Find additional kids_allowed slot
        # TODO: activate
        # match_kids_slot = find_surface_form(sys_line, ["děti", "dětí", "dětem", "dětmi"])
        # if match_kids_slot:
        #     num_additional_slot_value_error += 1
        #     logging.info(f"Slot Error: found additional value '{match_kids_slot}' for slot 'kids_allowed' in sentence '{sys_line_orig}'. DA is '{da_string}'")

    print("total number of DAs", len(das))
    print("problems", problems)
    print("valid slots", num_valid_slots_with_value)
    if num_valid_slots_with_value:
        SER = (num_missing_slot_value_error+num_additional_slot_value_error) / num_valid_slots_with_value
        print("SER", SER)
    else:
        logging.warning(f"Didn't find any valid slots")
        print("SER", 0)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)

    ap = ArgumentParser(description='Slot Error Rate evaluation for Czech restaurant information dataset')
    ap.add_argument('surface_forms_file', type=str, help='JSON file containing the surface forms for all slot values.')
    ap.add_argument('ref_file', type=str, help='References CSV file containing the dialogue acts (DAs) in the first column.')
    ap.add_argument('--sys_file', type=str, help='System output file to evaluate (text file with one output per line).')
    args = ap.parse_args()

    surface_forms, das, sys = load_data(args.surface_forms_file, args.ref_file, args.sys_file)

    evaluate(surface_forms, das, sys)