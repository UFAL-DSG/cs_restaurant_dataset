#!/usr/bin/env python3

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
    """Loads the data using helper functions. 
    For ref_file it loads it in correct format according to its extension"""
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
    """Parses one line of Dialogue Act in the form of "DA_TYPE(SLOT=VALUE,...)".

    Args:
        da (str): one dialogue act string

    Returns:
        dict: a dictionary containing the parsed information from the input DA string.

    Example:
        >>> parse_da("inform(good_for_meal='lunch or dinner',name=BarBar)")
        {'type': 'inform', 'attributes': {'good_for_meal': ['lunch', 'dinner'], 'name': ['BarBar']}}
    """

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

class Evaluator:
    """Main class for running the Slot Error Rate evaluation"""

    def __init__(self, surface_forms):
        # Main counters for the resulting SER
        self.num_valid_slot_values = 0
        self.num_missing_slot_value_error = 0
        self.num_additional_slot_value_error = 0

        # Counter for checking the coverage of this evaluator
        self.num_cannot_check_slot_values = 0

        # Remove the lemma and tags in the surface forms
        self.surface_forms = {slot: {lemma: [form.split("\t")[1] for form in forms] for lemma, forms in values.items()} for slot, values in surface_forms.items()}
        self.kids_surface_forms = ["děti", "dětí", "dětem", "dětmi"]
        if "price" in self.surface_forms:
            self.price_surface_forms = self.surface_forms["price"]["between _ and _ Kč"]
        else:
            self.price_surface_forms = []
            logging.error(f"No `price` key in the surface forms file. Please check the surface forms file.")

    def exact_match(self, sentence, substring):
        """Search for substring in sentence, if there is match return it.
        If not, return False."""
        substring = str(substring)
        if substring in sentence:
            return substring
        else:
            return False
    
    def regex_match(self, sentence, regex, group=0):
        """Search for regex match in sentence, if there is match return it.
        If not, return False."""
        matches = re.search(regex, sentence, re.IGNORECASE)
        if matches:
            return matches.group(group)
        else:
            return False

    def address_match(self, street_value, sentence, forms):
        """Search for address of form "Street Name 123" in sentence,
        if there is match return it. If not, return False."""
        street_name, street_num = street_value.rsplit(" ", 1)
        if street_name in forms:
            for test_name in forms[street_name]:
                test_address = f"{test_name} {street_num}"
                if test_address in sentence:
                    return test_address
        return False

    def surface_forms_match(self, sentence, forms):
        """Search for all forms (and capitalized variants) of a word in a sentence, 
        if there is match return it. If not, return False."""
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

    def remove_from_sentence(self, sentence, substring):
        """Remove a substring from a sentence. Deduplicates whitespaces."""
        if substring:
            new_sentence = "".join(sentence.split(substring))
            # Replace multiple spaces with one
            new_sentence = re.sub(' +',' ',new_sentence)
            assert new_sentence != sentence, f"didn't find match for substring {substring} in sentence {sentence}"
            return new_sentence
        else:
            return sentence
    
    def find_kids_negation(self, sys_line, negation_max_word_distance):
        """Looks for a word combination indicating kids_allowed=no in the input sentence"""
        negation_max_word_distance = str(negation_max_word_distance)
        match = self.regex_match(sys_line, r"\b(ne\w*) (?:\w+ ){0,"+negation_max_word_distance+r"}dět\w*", group=1)
        if not match:
            # (?!a ) is there because of "... a ..." conjunction
            match = self.regex_match(sys_line, r"dět\w* (?!a )(?:\w+ ){0,2}(ne\w+)", group=1)
        if not match:
            match = self.regex_match(sys_line, r"(zakáz\w*|zákaz\w*) (?:\w+ ){0,"+negation_max_word_distance+r"}dět\w*", group=1)
        if not match:
            match = self.regex_match(sys_line, r"dět\w* (?:\w+ ){0,"+negation_max_word_distance+r"}(zakáz\w*|zákaz\w*)", group=1)
        if not match:
            match = self.regex_match(sys_line, r"(bez) (?:\w+ ){0,3}dět\w*", group=1)
        return match
    
    def count_slot_missing_error(self, is_valid):
        """Adds to the total number of slot values and possibly to the number of errors"""
        self.num_valid_slot_values += 1
        if not is_valid:
            self.num_missing_slot_value_error += 1
    
    def log_slot_missing_error(self, is_valid, value, slot, sys_line, index):
        if not is_valid:
            logging.info(f"Slot Error: didn't find match for '{value}' for slot '{slot}' in instance {index}: '{sys_line}'")
    
    def log_additional_slot_error(self, substring, slot, sys_line, da_line, index):
        logging.info(f"Slot Error: found substring '{substring}' implying slot '{slot}' in instance {index}: '{sys_line}'. DA is '{da_line}'")

    def handle_kids_allowed(self, values, sys_line, da, slot, sys_line_orig, index):
        """Subroutine for the evaluate function, checks the kids_allowed slot"""
        match_kids_slot = self.surface_forms_match(sys_line, self.kids_surface_forms)

        # For two examples in the train set the value is missing but =yes is assumed
        if len(values) == 0:
            values = ["yes"]

        if len(values) == 1:
            value = values[0]
            negation_max_word_distance = 5
            # inform_no_match will very probably contain a negation
            # therefore we need to check smaller neighbourhood around "děti"
            if da["type"] == "inform_no_match":
                negation_max_word_distance = 3
            if value == "yes":
                match_kids_negation = self.find_kids_negation(sys_line, negation_max_word_distance)
                # the sentence needs to contain the word kids
                # but cannot contain negation before/after kids
                is_valid = match_kids_slot and not match_kids_negation
                self.count_slot_missing_error(is_valid)
                if is_valid:
                    sys_line = self.remove_from_sentence(sys_line, match_kids_slot)
                self.log_slot_missing_error(is_valid, value, slot, sys_line_orig, index)
            elif value == "no":
                match_kids_negation = self.find_kids_negation(sys_line, negation_max_word_distance)
                # the sentence needs to contain the word kids
                # and must contain negation before/after kids
                is_valid = match_kids_slot and match_kids_negation
                self.count_slot_missing_error(is_valid)
                if is_valid:
                    sys_line = self.remove_from_sentence(sys_line, match_kids_slot)
                    sys_line = self.remove_from_sentence(sys_line, match_kids_negation)
                self.log_slot_missing_error(is_valid, value, slot, sys_line_orig, index)
            elif value == "dont_care":
                self.num_cannot_check_slot_values += 1
                logging.debug(f"Coverage problem: We cannot handle kids_allowed='dont_care'")
            elif value == "none":
                self.num_cannot_check_slot_values += 1
                logging.debug(f"Coverage problem: We cannot handle kids_allowed='none'")
            else:
                assert False, f"Invalid value {value} for kids_allowed"

        if len(values) == 2:
            if set(values) == {"yes", "no"}:
                self.num_cannot_check_slot_values += 2
                logging.debug(f"Coverage problem: We cannot handle kids_allowed='yes or no'")
            elif set(values) == {"dont_care", "yes"}:
                self.num_cannot_check_slot_values += 2
                logging.debug(f"Coverage problem: We cannot handle kids_allowed='yes',kids_allowed='dont_care'")
            else:
                assert False, f"Invalid value {values} for kids_allowed"
        
        return sys_line

    def handle_price(self, values, sys_line, da, slot, sys_line_orig, index):
        """Subroutine for the evaluate function, checks the price slot"""
        for value in values:
            if "between" in value:
                # remove text around prices
                value = value[8:-3]
                price1, price2 = value.split(" and ")
                match = False
                for _form in self.price_surface_forms:
                    form = _form.split("_")
                    assert len(form) == 3, _form
                    czech_between_string = form[0] + price1 + form[1] + price2 + form[2]
                    match = self.exact_match(sys_line, czech_between_string)
                    if match:
                        break
            else:
                match = self.exact_match(sys_line, value)
            
            self.count_slot_missing_error(match)
            sys_line = self.remove_from_sentence(sys_line, match)
            self.log_slot_missing_error(match, value, slot, sys_line_orig, index)
        return sys_line

    def evaluate(self, das, sys):
        """Computes the Slot Error Rate.

        Args:
            das (List[str]): Dialogue Act lines
            sys (List[str]): System output lines
        """
        self.num_cannot_check_slot_values = 0
        num_total_num_of_slot_values = 0
        num_type_slots = 0

        self.num_valid_slot_values = 0
        self.num_missing_slot_value_error = 0
        self.num_additional_slot_value_error = 0

        for index, (da_line, sys_line_orig) in enumerate(zip(das, sys)):
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
                    self.num_cannot_check_slot_values += 1
                    logging.debug(f"Coverage problem: We cannot handle {slot} with no value.")
                    continue
                
                # Big switch statement for handling different slot types
                if slot == "type":
                    num_type_slots += 1
                    self.num_cannot_check_slot_values += 1
                    # We don't log the coverage problem here because we don't have to check this slot
                    continue
                elif slot == "kids_allowed":
                    sys_line = self.handle_kids_allowed(values, sys_line, da, slot, sys_line_orig, index)
                elif slot in ["phone", "count", "postcode"]:
                    # TODO: For count we might want to implement checking numerals (such as "dvě", "tři", ...)
                    for value in values:
                        match = self.exact_match(sys_line, value)
                        self.count_slot_missing_error(match)
                        sys_line = self.remove_from_sentence(sys_line, match)
                        self.log_slot_missing_error(match, value, slot, sys_line_orig, index)
                elif slot == "address":
                    for value in values:
                        match = self.address_match(value, sys_line, self.surface_forms["street"])
                        self.count_slot_missing_error(match)
                        sys_line = self.remove_from_sentence(sys_line, match)
                        self.log_slot_missing_error(match, value, slot, sys_line_orig, index)
                elif slot == "price":
                    sys_line = self.handle_price(values, sys_line, da, slot, sys_line_orig, index)
                elif slot in self.surface_forms:
                    for value in values:
                        if value in self.surface_forms[slot]:
                            match = self.surface_forms_match(sys_line, self.surface_forms[slot][value])
                            self.count_slot_missing_error(match)
                            sys_line = self.remove_from_sentence(sys_line, match)
                            self.log_slot_missing_error(match, value, slot, sys_line_orig, index)
                        else:
                            # TODO: handle dont_care
                            if value == "dont_care":
                                self.num_cannot_check_slot_values += 1
                                logging.debug(f"Coverage problem: We cannot handle value 'dont_care' for slot {slot}")
                            # TODO: handle none
                            if value == "none":
                                self.num_cannot_check_slot_values += 1
                                logging.debug(f"Coverage problem: We cannot handle value 'none' for slot {slot}")
                else:
                    logging.error(f"Invalid slot in the parsed attributes of DA '{da_line}': {slot}")
                    pass
            
            
            # Find additional slot values that are not supposed to be in the system output
            for surface_forms_slot, surface_forms_values in self.surface_forms.items():
                # Do not check those slots that are inside the DA without any value
                # These often list some or all of the value keywords to raise a question to the user
                if surface_forms_slot in attributes and attributes[surface_forms_slot] == []:
                    continue
                # Do not check the good_for_meal slot for DA goodbye().
                # To avoid false additional error in sentences such as "Přeji dobrou chuť k večeři ."
                if da["type"] == "goodbye" and surface_forms_slot == "good_for_meal":
                    continue

                if surface_forms_slot == "price_range":
                    continue
                for forms in surface_forms_values.values():
                    match = self.surface_forms_match(sys_line, forms)
                    if match:
                        self.log_additional_slot_error(match, surface_forms_slot, sys_line_orig, da_line, index)
                        self.num_additional_slot_value_error += 1

            # Find additional kids_allowed slot
            match_kids_slot = self.surface_forms_match(sys_line, self.kids_surface_forms)
            if match_kids_slot and ("kids_allowed" not in attributes or attributes["kids_allowed"] in [["yes"], ["no"]]):
                self.log_additional_slot_error(match_kids_slot, "kids_allowed", sys_line_orig, da_line, index)
                self.num_additional_slot_value_error += 1

        logging.info(f"Total number of DAs: {len(das)}")

        diff_cannot_check = num_total_num_of_slot_values - self.num_valid_slot_values
        assert self.num_cannot_check_slot_values == diff_cannot_check, "The number of slots we know we cannot check should equal the total number of slots and the number of slots that we correctly handled"

        logging.info(f"Total number of slots: {num_total_num_of_slot_values}")
        logging.info(f"Slots that we cannot check: {self.num_cannot_check_slot_values}, out of which {num_type_slots} are 'type=restaurant' slots")
        slot_errors = self.num_missing_slot_value_error+self.num_additional_slot_value_error
        if num_total_num_of_slot_values:
            SER = slot_errors / num_total_num_of_slot_values
        else:
            logging.warning(f"Didn't find any valid slots")
            SER = 0

        return SER, slot_errors, self.num_missing_slot_value_error, self.num_additional_slot_value_error

def main():
    ap = ArgumentParser(description='Slot Error Rate evaluation for Czech restaurant information dataset')
    ap.add_argument('surface_forms_file', type=str, help='JSON file containing the surface forms for all slot values.')
    ap.add_argument('ref_file', type=str, help='References CSV file containing the dialogue acts (DAs) in the first column.')
    ap.add_argument('--sys_file', type=str, help='System output file to evaluate (text file with one output per line). '+
                    'If not supplied we use the reference realizations from the ref_file as the system output. '+
                    '(useful for testing and finding mistakes in the dataset)')
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

    ser = Evaluator(surface_forms)
    ser_score, slot_errors, num_missing_slot_value_error, num_additional_slot_value_error = ser.evaluate(das, sys)

    print("Missing Slot Errors: ", num_missing_slot_value_error)
    print("Additional Slot Errors: ", num_additional_slot_value_error)
    print("Total Slot Errors: ", slot_errors)
    print("SER:", ser_score)

if __name__ == '__main__':
    main()