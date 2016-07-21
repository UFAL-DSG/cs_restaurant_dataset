#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import re
import sys
import codecs
from argparse import ArgumentParser
from localize import load_dais, write_das, DAI
from delexicalize import load_texts
import kenlm
import numpy as np
from delexicalize import Delexicalizer


def da_key(da):
    return "&".join([unicode(dai) for dai in sorted(da, key=lambda dai: dai.slot)])


def write_texts(file_name, texts):
    with codecs.open(file_name, 'wb', 'UTF-8') as fh:
        for text in texts:
            print >> fh, text


class Expander(object):

    def __init__(self, args):
        # read inputs
        self.orig_das = load_dais(args.orig_das)

        self.transl_das = load_dais(args.transl_das)
        self.transl_texts = load_texts(args.transl_texts)

        # run delexicalization, store tokens + lemmas + tags, delex DAs
        self.delexicalizer = Delexicalizer(args.slots, args.surface_forms, args.tagger_model,
                                           output_format='factors')
        self.delex_texts = []
        self.delex_das = []
        for counter, (da, text) in enumerate(zip(self.transl_das, self.transl_texts)):
            self.delex_texts.append(self.delexicalizer.delexicalize_text(text, da, counter))
            self.delex_das.append(self.delexicalizer.delexicalize_da(da))

        self.values = self.get_values(self.transl_das)

        self.orig_da_positions = self.group_das(self.orig_das, check_delex=True)
        self.transl_da_positions = self.group_das(self.delex_das)

        self.out_texts = [None] * len(self.orig_das)
        self.out_delex_texts = [None] * len(self.orig_das)
        self.out_das = [None] * len(self.orig_das)
        self.out_delex_das = [None] * len(self.orig_das)

        self.lm = kenlm.Model(args.lm)

        self.out_texts_file = args.out_texts
        self.out_delex_texts_file = args.out_delex_texts
        self.out_das_file = args.out_das
        self.out_delex_das_file = args.out_delex_das

    def expand(self):
        for da_key, (da, orig_pos) in self.orig_da_positions.iteritems():
            _, transl_pos = self.transl_da_positions[da_key]
            self.expand_da(da, orig_pos, transl_pos)

    def expand_da(self, da, orig_pos, transl_pos):
        # count # of different realizations for the given DA
        orig_count = len(orig_pos)
        transl_count = len(transl_pos)

        assert(orig_count > 0)
        assert(transl_count > 0)
        assert(transl_count <= orig_count)

        # score all realizations by a LM
        scores = []
        for pos in transl_pos:
            scores.append(self.lm.score(" ".join([lemma for _, lemma, _ in self.delex_texts[pos]])))

        # normalize scores into a prob dist (~ apply softmax)
        max_score = max(scores)
        scores = np.array(scores) - max_score
        scores = np.exp(scores)
        scores /= np.sum(scores)

        # save the original stuff into the new positions
        for opos_, tpos_ in zip(orig_pos, transl_pos):
            self.out_texts[opos_] = self.transl_texts[tpos_]
            self.out_delex_texts[opos_] = [tok for tok, _, _ in self.delex_texts[tpos_]]
            self.out_das[opos_] = self.transl_das[tpos_]
            self.out_delex_das[opos_] = self.delex_das[tpos_]

        # sample missing stuff from that distribution
        # TODO mark them to be checked
        repls = np.random.choice(transl_pos, orig_count - transl_count, p=scores)
        for opos_, tpos_ in zip(orig_pos[transl_count:], repls):
            relex_text, relex_da = self.relexicalize(self.delex_texts[tpos_],
                                                     self.delex_das[tpos_])
            self.out_texts[opos_] = relex_text
            self.out_delex_texts[opos_] = self.delex_texts[tpos_]
            self.out_das[opos_] = relex_da
            self.out_delex_das[opos_] = self.delex_das[tpos_]

    def relexicalize(self, text, da):
        text = " ".join([tok for tok, _, _ in text])
        text = re.sub(r' ([?.,\'])', r'\1', text)
        da = [DAI(dai.dat, dai.slot, dai.value) for dai in da]  # deep copy
        for dai in da:
            if not dai.value or dai.value in ['dont_care', 'none', 'yes', 'no', 'yes or no']:
                continue
            # relexicalize DA
            dai.value = np.random.choice(self.values[dai.slot])
            # relexicalize text
            # TODO inflect
            # TODO care about the PoS
            text = re.sub(r'X-' + dai.slot + '(/[^ ]*)?', dai.value, text)
        return text, da

    def group_das(self, das, check_delex=False):
        groups = {}
        for cur_pos, da in enumerate(das):
            key = da_key(da)
            if check_delex:
                delex_da = self.delexicalizer.delexicalize_da(da)
                delex_key = da_key(delex_da)
                if delex_key != key:
                    print >> sys.stderr, "DA not properly delexicalized: %d - %s" % (cur_pos, key)
                    da = delex_da
                    key = delex_key
            pos = groups.get(key, (None, []))[1]
            pos.append(cur_pos)
            groups[key] = (da, pos)
        return groups

    def get_values(self, das):
        ret = {}
        for da in das:
            for dai in da:
                if dai.slot not in ret:
                    ret[dai.slot] = set()
                ret[dai.slot].add(dai.value)
        for slot in ret.keys():
            ret[slot] = list(ret[slot])
        return ret

    def write_outputs(self):
        write_texts(self.out_texts_file, self.out_texts)
        write_texts(self.out_delex_texts_file, self.out_delex_texts)
        write_das(self.out_das_file, self.out_das)
        write_das(self.out_delex_das_file, self.out_delex_das)


def main():

    ap = ArgumentParser()

    ap.add_argument('-l', '--lm', type=str, help='KenLM language model on lowercased, delexicalized,' +
                    'tokenized texts')
    ap.add_argument('-s', '--slots', type=str, help='List of slots to delexicalize')
    ap.add_argument('-f', '--surface-forms', type=str, help='Input file with surface forms for slot values')
    ap.add_argument('-t', '--tagger-model', type=str, help='Path to Morphodita tagger model')

    ap.add_argument('orig_das', type=str, help='Input delexicalized original DAs')

    ap.add_argument('transl_das', type=str, help='Input lexicalized translated DAs')
    ap.add_argument('transl_texts', type=str, help='Input lexicalized translated texts')

    ap.add_argument('out_texts', type=str, help='Output lexicalized texts')
    ap.add_argument('out_delex_texts', type=str, help='Output delexicalized texts')

    ap.add_argument('out_das', type=str, help='Output lexicalized DAs')
    ap.add_argument('out_delex_das', type=str, help='Output delexicalized DAs')

    args = ap.parse_args()

    ex = Expander(args)
    ex.expand()
    ex.write_outputs()


if __name__ == '__main__':
    main()