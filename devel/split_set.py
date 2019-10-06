#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import codecs
import json
import re
from argparse import ArgumentParser
from collections import deque, namedtuple
from itertools import islice

import numpy as np
import random
import pandas as pd

from ufal.morphodita import Tagger, Forms, TaggedLemma, TaggedLemmas, TokenRanges, Analyses, Indices

import sys
import os
sys.path.insert(0, os.path.abspath('../../'))  # add tgen main directory to modules path
from tgen.logf import log_info
from tgen.data import Abst, DAI, DA

# Start IPdb on error in interactive mode
from tgen.debug import exc_info_hook
import sys
sys.excepthook = exc_info_hook


Inst = namedtuple('Inst', ['da', 'text', 'delex_da', 'delex_text', 'abst'])


class Reader(object):

    def __init__(self, tagger_model, abst_slots):
        self._tagger = Tagger.load(tagger_model)
        self._analyzer = self._tagger.getMorpho()
        self._tokenizer = self._tagger.newTokenizer()
        self._abst_slots = set(abst_slots.split(','))

        self._forms_buf = Forms()
        self._tokens_buf = TokenRanges()
        self._analyses_buf = Analyses()
        self._indices_buf = Indices()

        self._sf_dict = {}
        self._rev_sf_dict = {}
        self._sf_max_len = 0

    def load_surface_forms(self, surface_forms_fname):
        """Load all proper name surface forms from a file."""
        with codecs.open(surface_forms_fname, 'rb', 'UTF-8') as fh:
            data = json.load(fh)
        for slot, values in data.items():
            for value in values.keys():
                for surface_form in values[value]:
                    lemma, form, tag = surface_form.split("\t")
                    form_toks = form.lower().split(" ")
                    if slot == 'street':  # add street number placeholders to addresses
                        lemma += ' _'
                        form_toks.append('_')
                    form_toks = tuple(form_toks)
                    self._sf_max_len = max((self._sf_max_len, len(form_toks)))
                    if form_toks not in self._sf_dict:
                        self._sf_dict[form_toks] = []
                    self._sf_dict[form_toks].append((lemma, tag))
                    self._rev_sf_dict[(form.lower(), lemma, tag)] = (slot, value)

    def _get_surface_form_taggedlemmas(self, forms_in):
        """Given a tokens deque, return the form & list of tagged lemmas (analyses)
        for the proper name in the list of forms at the current position, if applicable.
        If there is no proper name at the beginning of the tokens deque, return (None, None).

        @param forms_in: a deque of forms tokens
        @return: (form, tagged lemmas list) or (None, None)
        """
        for test_len in range(min(self._sf_max_len, len(forms_in)), 0, -1):
            # test the string, handle number placeholders
            full_substr = [form for form in islice(forms_in, 0, test_len)]
            test_substr = tuple(['_' if re.match(r'^[0-9]+$', form) else form.lower()
                                 for form in full_substr])
            if test_substr in self._sf_dict:
                tls = TaggedLemmas()
                nums = [num for num in full_substr if re.match(r'^[0-9]+$', num)]
                for lemma, tag in self._sf_dict[test_substr]:
                    tls.push_back(TaggedLemma())
                    for num in nums:  # replace number placeholders by actual values
                        lemma = re.sub(r'_', num, lemma, count=1)
                    tls[-1].lemma = lemma
                    tls[-1].tag = tag
                for _ in range(len(test_substr)):  # move on in the sentence
                    forms_in.popleft()
                return " ".join(full_substr), tls
        return None, None

    def analyze(self, sent):
        """Perform morphological analysis on the given sentence, preferring analyses from the
        list of surface forms. Return a list of tuples (form, lemma, tag)."""
        self._tokenizer.setText(sent)
        analyzed = []
        while self._tokenizer.nextSentence(self._forms_buf, self._tokens_buf):

            forms_in = deque(self._forms_buf)
            self._forms_buf.resize(0)
            self._analyses_buf.resize(0)  # reset previous analyses

            while forms_in:
                form, analyses = self._get_surface_form_taggedlemmas(forms_in)
                if form:
                    # our custom analysis
                    self._analyses_buf.push_back(analyses)
                else:
                    # Morphodita analysis
                    form = forms_in.popleft()
                    analyses = TaggedLemmas()
                    self._analyzer.analyze(form, 1, analyses)
                    for i in range(len(analyses)):  # shorten lemmas (must access the vector directly)
                        analyses[i].lemma = self._analyzer.rawLemma(analyses[i].lemma)
                    self._analyses_buf.push_back(analyses)

                self._forms_buf.push_back(form)

            # tag according to the given analysis
            self._tagger.tagAnalyzed(self._forms_buf, self._analyses_buf, self._indices_buf)
            analyzed.extend([(f, a[idx].lemma, a[idx].tag)
                             for (f, a, idx)
                             in zip(self._forms_buf, self._analyses_buf, self._indices_buf)])
        return analyzed

    def process_dataset(self, input_data):
        """Load DAs & sentences, obtain abstraction instructions, and store it all in member
        variables (to be used later by writing methods).
        @param input_data: path to the input JSON file with the data
        """
        # load data from JSON
        self._das = []
        self._texts = []
        with codecs.open(input_data, 'r', encoding='UTF-8') as fh:
            data = json.load(fh)
            for inst in data:
                da = DA.parse(inst['da'])
                da.sort()
                self._das.append(da)
                self._texts.append(self.analyze(inst['text']))

        # delexicalize DAs and sentences
        self._create_delex_texts()
        self._create_delex_das()

        # return the result
        out = []
        for da, text, delex_da, delex_text, abst in zip(self._das, self._texts, self._delex_das, self._delex_texts, self._absts):
            out.append(Inst(da, text, delex_da, delex_text, abst))
        return out

    def _create_delex_texts(self):
        """Delexicalize texts in the buffers and save them separately in the member variables,
        along with the delexicalization instructions used for the operation."""
        self._delex_texts = []
        self._absts = []
        for text_idx, (text, da) in enumerate(zip(self._texts, self._das)):
            delex_text = []
            absts = []
            # do the delexicalization, keep track of which slots we used
            for tok_idx, (form, lemma, tag) in enumerate(text):
                # abstract away from numbers
                abst_form = re.sub(r'( |^)[0-9]+( |$)', r'\1_\2', form.lower())
                abst_lemma = re.sub(r'( |^)[0-9]+( |$)', r'\1_\2', lemma)
                # try to find if the surface form belongs to some slot
                slot, value = self._rev_sf_dict.get((abst_form, abst_lemma, tag), (None, None))
                # if we found a slot, get back the numbers
                if slot:
                    for num_match in re.finditer(r'(?: |^)([0-9]+)(?: |$)', lemma):
                        value = re.sub(r'_', num_match.group(1), value, count=1)
                # fall back to directly comparing against the DA value
                else:
                    slot = da.has_value(lemma)
                    value = lemma

                # if we found something, delexicalize it (check if the value corresponds to the DA!)
                if (slot and slot in self._abst_slots and
                        da.value_for_slot(slot) not in [None, 'none', 'dont_care'] and
                        value in da.value_for_slot(slot)):
                    delex_text.append(('X-' + slot, 'X-' + slot, tag))
                    absts.append(Abst(slot, value, form, tok_idx, tok_idx + 1))
                # otherwise keep the token as it is
                else:
                    delex_text.append((form, lemma, tag))
            # fix coordinated delexicalized values
            self._delex_fix_coords(delex_text, da, absts)
            covered_slots = set([a.slot for a in absts])
            # check and warn if we left isomething non-delexicalized
            for dai in da:
                if (dai.slot in self._abst_slots and
                        dai.value not in [None, 'none', 'dont_care'] and
                        dai.slot not in covered_slots):
                    log_info("Cannot delexicalize slot  %s  at %d:\nDA: %s\nTx: %s\n" %
                             (dai.slot,
                              text_idx,
                              str(da),
                              " ".join([form for form, _, _ in text])))
            # save the delexicalized text and the delexicalization instructions
            self._delex_texts.append(delex_text)
            self._absts.append(absts)

    def _delex_fix_coords(self, text, da, absts):
        """Fix (merge) coordinated values in delexicalized text (X-slot and X-slot -> X-slot).
        Modifies the input list directly.

        @param text: list of form-lemma-tag tokens of the delexicalized sentence
        @return: None
        """
        idx = 0
        while idx < len(absts) - 1:
            if (absts[idx].slot == absts[idx+1].slot and
                    absts[idx].end + 1 == absts[idx + 1].start and
                    re.search(r' (and|or) ', da.value_for_slot(absts[idx].slot))):
                for abst in absts[idx+2:]:
                    abst.start -= 2
                    abst.end -= 2
                absts[idx].value = da.value_for_slot(absts[idx].slot)
                del text[absts[idx].end:absts[idx + 1].end]
                del absts[idx + 1]
            idx += 1

    def _create_delex_das(self):
        """Delexicalize DAs in the buffers, save them separately."""
        out = []
        for da in self._das:
            delex_da = DA()
            for dai in da:
                delex_dai = DAI(dai.da_type, dai.slot,
                                'X-' + dai.slot
                                if (dai.value not in [None, 'none', 'dont_care'] and
                                    dai.slot in self._abst_slots)
                                else dai.value)
                delex_da.append(delex_dai)
            out.append(delex_da)
        self._delex_das = out


class Writer(object):

    def __init__(self):
        pass

    def _insts_to_records(self, insts):
        return [{"da": inst.da.to_cambridge_da_string(),
                 "delex_da": inst.delex_da.to_cambridge_da_string(),
                 "text": " ".join([w[0] for w in inst.text]),
                 "delex_text": " ".join([w[0] for w in inst.delex_text])}
                for inst in insts]

    def write_json(self, data_file, insts):
        with codecs.open(data_file, 'w', 'UTF-8') as fh:
            json.dump(self._insts_to_records(insts), fh, indent=4, ensure_ascii=False)

    def write_csv(self, data_file, insts):
        data = pd.DataFrame.from_records(self._insts_to_records(insts))
        data.to_csv(data_file, sep=",", encoding="UTF-8", index=False, columns=["da", "delex_da", "text", "delex_text"])


def split_roughly_equally(da_to_insts, num_parts):
    """Split a DA-to-inst mapping into num_part roughly equal-sized parts,
    keeping the division along the mapping."""
    parts = [[] for _ in range(num_parts)]
    # first-fit decreasing algorithm: sort decreasing by size, always add to currently smallest
    for da, insts in sorted(list(da_to_insts.items()), key=lambda item: len(item[1]), reverse=True):
        next_part = np.argmin([len(g) for g in parts])  # find the part that has least items
        parts[next_part].extend(insts)  # give it the instances
    return parts


def convert(args):
    """Main conversion function (using command-line arguments as parsed by Argparse)."""
    log_info('Loading...')
    reader = Reader(args.tagger_model, args.abst_slots)
    reader.load_surface_forms(args.surface_forms)
    log_info('Processing input files...')
    insts = reader.process_dataset(args.input_data)
    log_info('Loaded %d data items.' % len(insts))

    # regroup data by delex DA & split from there
    if args.split:
        # mapping delex. DA to instance
        da_to_insts = {}
        for inst in insts:
            da_to_insts[inst.delex_da] = da_to_insts.get(inst.delex_da, []) + [inst]

        data_sizes = [int(size) for size in args.split.split(':')]
        num_parts = sum(data_sizes)
        groups = [[] for _ in range(len(data_sizes))]
        for da_type in sorted(set([inst.delex_da.dais[0].da_type for inst in insts])):
            # split instances of given DA type into equally sized parts
            insts_for_da_type = {da: insts for da, insts in da_to_insts.items() if da.dais[0].da_type == da_type}
            parts_for_da_type = split_roughly_equally(insts_for_da_type, num_parts)

            # shuffle the parts, keeping the first at its place (if there's only 1 DA, it'll end up in training)
            all_but_1st = parts_for_da_type[1:]
            random.shuffle(all_but_1st)
            parts_for_da_type = parts_for_da_type[:1] + all_but_1st

            # merge parts into groups sequentially, e.g. add to 1, 2, 3, 1, 1 for size parts 3:1:1
            trg_idx = 0
            src_idx = 0
            added = [0] * len(data_sizes)
            while src_idx < num_parts:
                if added[trg_idx] < data_sizes[trg_idx]:
                    groups[trg_idx].extend(parts_for_da_type[src_idx])
                    added[trg_idx] += 1
                    src_idx += 1
                trg_idx = (trg_idx + 1) % len(data_sizes)

        # shuffle the order in the resulting groups
        for group in groups:
            random.shuffle(group)

        # get output file name prefixes
        out_names = re.split(r'[, ]+', args.out_prefix)

    # use just one group -- containing all the data
    else:
        groups = [insts]
        out_names = [args.out_prefix]

    # write all data groups
    # outputs: plain delex, plain lex, interleaved delex & lex, CoNLL-U delex & lex, DAs, abstrs
    writer = Writer()
    for group, group_name in zip(groups, out_names):
        log_info('Writing %s (size: %d)...' % (group_name, len(group)))

        writer.write_json(group_name + '.json', group)
        writer.write_csv(group_name + '.csv', group)


if __name__ == '__main__':

    random.seed(1206)
    ap = ArgumentParser()

    ap.add_argument('tagger_model', type=str, help='MorphoDiTa tagger model')
    ap.add_argument('surface_forms', type=str, help='Input JSON with base forms')
    ap.add_argument('input_data', type=str, help='Input data JSON')
    ap.add_argument('out_prefix', help='Output files name prefix(es - when used with -s, comma-separated)')
    ap.add_argument('-a', '--abst-slots', help='List of slots to delexicalize/abstract (comma-separated)')
    ap.add_argument('-s', '--split', help='Colon-separated sizes of splits (e.g.: 3:1:1)')

    args = ap.parse_args()
    convert(args)
