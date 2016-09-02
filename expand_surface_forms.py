#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Expanding surface forms into all cases. Use this on a JSON of slots, values, and possible
surface form lemmas. The output must be postprocessed by hand (as morphological dictionary
is lacking on restaurant names and similar).

Czech-specific + SDS-specific, partially domain-specific (in terms of which inflection forms
are produced)
"""

from __future__ import unicode_literals

import itertools
import codecs
import json
import re
from argparse import ArgumentParser

from util import Analyzer, Generator, remove_dups_stable

import sys
from tgen.debug import exc_info_hook
from tgen.logf import log_info
# Start IPdb on error in interactive mode
sys.excepthook = exc_info_hook
sys.stderr = codecs.getwriter('UTF-8')(sys.stderr)


class ExpandSurfaceForms(object):

    def __init__(self, tagger_model, generator_dict):
        self._analyzer = Analyzer(tagger_model)
        self._generator = Generator(generator_dict)

    def process_file(self, input_fname, output_fname):
        """Expand surface forms in one JSON file.

        @param input_fname: input JSON file (slots -> values -> possible surface form lemmas)
        @param output_fname: output JSON file (slots -> values -> surface forms in all cases)
        """
        # read input
        with codecs.open(input_fname, 'rb', 'UTF-8') as fh:
            data = json.load(fh)
        # process (expand all surface forms)
        for slot, values in data.iteritems():
            for value in values.keys():
                variants = values[value]
                expanded = []
                for variant in variants:
                    # analyze the word
                    words = self._analyzer.analyze(variant)
                    # ganther required inflection forms
                    # verbs: 2nd person present + infinitive
                    if words[0][2].startswith('V'):
                        infls = [{'person': '2'}, {'person': '-'}]
                    # nouns/adjectives: all cases (except vocative)
                    else:
                        infls = [{'case': '1'}, {'case': '2'}, {'case': '3'},
                                 {'case': '4'}, {'case': '6'}, {'case': '7'}]
                        adj_adv = (slot != 'street' and
                                   all(re.match('^[AD]', word[2]) for word in words))
                        # all numbers for some cases (domain specific) and adjective/adverb
                        if (adj_adv or
                                re.search(r'(^| )(snídaně|oběd|večeře|brunch)( |$)', variant)):
                            new_infls = []
                            for infl in infls:
                                for number in ['S', 'P']:
                                    new_infl = infl.copy()
                                    new_infl.update({'number': number})
                                    new_infls.append(new_infl)
                            infls = new_infls
                        # all genders for adjective/adverb only (except street names)
                        if adj_adv:
                            new_infls = []
                            for infl in infls:
                                for gender in ['M', 'I', 'F', 'N']:
                                    new_infl = infl.copy()
                                    new_infl.update({'gender': gender})
                                    new_infls.append(new_infl)
                            infls = new_infls
                    # do the inflection
                    for infl in infls:
                        forms_tags = self._generator.inflect(words, **infl)
                        # use all possible combinations if there are more variants
                        inflected = [(' '.join([form for form, _ in var]) +
                                      "\t" +
                                      self.get_main_tag([tag for _, tag in var]))
                                     for var in itertools.product(*forms_tags)]
                        expanded.extend(inflected)
                # remove duplicates
                expanded = [var for var in remove_dups_stable(expanded)]
                values[value] = expanded
        # write output
        with codecs.open(output_fname, 'wb', 'UTF-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4)

    def get_main_tag(self, tags):
        """Given a NE, get the main tag (typically a noun)"""
        # TODO better handling of "U Konšelů" and similar
        if all(re.match(r'^[NA]', t) for t in tags):
            tag = next(iter(reversed([t for t in tags if re.match(r'....[2-7]', t)])), None)
            if not tag:
                tag = next(iter(reversed([t for t in tags if re.match(r'....1', t)])), None)
            if tag:
                return tag

        elif (re.match(r'^[NA]', tags[0]) or
                (len(tags) > 1 and
                 re.match(r'^D', tags[0]) and
                 re.match(r'^[NA]', tags[1]))):
            tag = next(iter([t for t in tags if re.match(r'....[1-7]', t)]), None)
            if tag:
                return tag

        # default to first noun
        return tags[0]


def main():
    ap = ArgumentParser()

    ap.add_argument('tagger_model', type=str, help='MorphoDiTa tagger model')
    ap.add_argument('generator_dict', type=str, help='MorphoDiTa morphological generation dictionary')

    ap.add_argument('input_file', type=str, help='Input JSON with base forms')
    ap.add_argument('output_file', type=str, help='Output JSON with expanded forms and tags')

    args = ap.parse_args()

    ex = ExpandSurfaceForms(args.tagger_model, args.generator_dict)
    ex.process_file(args.input_file, args.output_file)


if __name__ == '__main__':
    main()
