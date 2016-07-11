#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import codecs
import re
from argparse import ArgumentParser

from itertools import product
from localize import load_dais, write_toks
from morpho import Analyzer, trunc_lemma
import sys
import json

from tgen.debug import exc_info_hook
# Start IPdb on error in interactive mode
sys.excepthook = exc_info_hook
sys.stderr = codecs.getwriter('UTF-8')(sys.stderr)

def sublist_pos(needle, haystack):
    n = len(needle)
    for pos in xrange(len(haystack)-n+1):
        if haystack[pos:pos+n] == needle:
            return pos
    return -1


def load_texts(file_name):
    data = []
    with codecs.open(file_name, 'r', encoding='UTF-8') as fh:
        for line in fh:
            line = line.strip()
            data.append(line)
    return data


class Delexicalizer(object):

    def __init__(self, slots, surface_forms, tagger_model, lemma_output):
        self.slots = slots
        self.surface_forms = surface_forms
        self.analyzer = Analyzer(tagger_model)
        self.lemma_output = lemma_output

    def delexicalize(self, text, da, counter=-1):
        analysis = self.analyzer.analyze(text)
        lemmas = [trunc_lemma(tok[1]).lower() for tok in analysis]
        tags = [tok[2] for tok in analysis]
        delex = [tok[0] for tok in analysis]
        for dai in da:
            if dai.slot not in self.slots and (dai.slot != 'address' or 'street' not in self.slots):
                continue
            if not dai.value or dai.value in ['dont care', 'dont_care', 'none']:
                continue
            surface_forms = self.get_surface_forms(dai.slot, dai.value)

            found = False
            for sf in surface_forms:
                pos = sublist_pos(sf, lemmas)
                if pos != -1:
                    found = True
                    form = self.get_form(tags, pos, sf)
                    delex[pos] = 'X-' + dai.slot + form
                    delex[pos+1:pos+len(sf)] = [None] * (len(sf) - 1)
                    break

            if not found:
                print >> sys.stderr, unicode(counter) + ': Not found: ' + dai.value + ' | ' + unicode(da) + ' | ' + text
                print >> sys.stderr, 'Lemmas: ' + ' '.join(lemmas)
                print >> sys.stderr

        if self.lemma_output:
            return [re.sub(r'/.*', r'', tok) if tok.startswith('X-') else lemma + (".NEG" if tag[10] == "N" else "")
                    for tok, lemma, tag in zip(delex, lemmas, tags)
                    if tok is not None]
        return [tok for tok in delex if tok is not None]

    def get_surface_forms(self, slot, value):
        if slot == 'price':
            prices = re.findall(r'[0-9]+', value)
            value_temp = re.sub(r'[0-9]+', r'_', value)
            surface_forms = self.surface_forms[slot][value_temp]
            for price in prices:
                surface_forms = [re.sub(r'_', price, vt, count=1) for vt in surface_forms]
            return [sf.split(' ') for sf in surface_forms]

        if re.search(r'\s+(and|or)\s+', value):
            sub_sf = [self.get_surface_forms(slot, subval)
                      for subval in re.split(r'\s*(?:and|or)\s*', value)]
            for pos in xrange(len(sub_sf)-1):
                sub_sf.insert(2*pos+1, [['a'], ['nebo'], ['i'], ['či']])
            return [[tok for sublist in sf_var for tok in sublist] for sf_var in product(*sub_sf)]

        if slot == 'address':
            street = ' '.join(value.split(' ')[:-1])
            num = value.split(' ')[-1]
            return [sf.split(' ') + [num]
                    for sf in self.surface_forms['street'][street]]

        elif slot in self.surface_forms:
            return [sf.split(' ') for sf in self.surface_forms[slot][value]]
        else:
            return [value.split(' ')]

    def get_form(self, tags, pos, sf):
        if pos > 0 and re.match(r'R...([0-9])', tags[pos-1]):
            return '/n:' + tags[pos-1][4]
        if all(re.match(r'^[NA]', t) for t in tags[pos:pos+len(sf)]):
            tag = next(iter(reversed([t for t in tags[pos:pos+len(sf)] if re.match(r'....[1-7]', t)])), None)
            if not tag:
                return ''
            return '/n:' + tag[4]
        if re.match(r'^[NA]', tags[pos]):
            tag = next(iter([t for t in tags[pos:pos+len(sf)] if re.match(r'....[1-7]', t)]), None)
            if not tag:
                return
            return '/n:' + tag[4]

        if re.match(r'^V', tags[pos]):
            return '/v:fin'

        return ''


def main():

    ap = ArgumentParser()

    ap.add_argument('-s', '--slots', type=str, help='List of slots to delexicalize')
    ap.add_argument('-f', '--surface-forms', type=str, help='Input file with surface forms for slot values')
    ap.add_argument('-t', '--tagger-model', type=str, help='Path to Morphodita tagger model')
    ap.add_argument('-l', '--lemma-output', action='store_true', help='Output only lemmas instead of tokens?')
    ap.add_argument('text_file', type=str, help='Input lexicalized text file')
    ap.add_argument('da_file', type=str, help='Input DA file')
    ap.add_argument('out_file', type=str, help='Output delexicalized text file')

    args = ap.parse_args()

    if args.surface_forms:
        with codecs.open(args.surface_forms, 'rb', 'UTF-8') as fh:
            surface_forms = json.load(fh)
    else:
        surface_forms = None

    delex = Delexicalizer(args.slots.split(','), surface_forms, args.tagger_model, args.lemma_output)

    texts = load_texts(args.text_file)
    das = load_dais(args.da_file)
    delexs = []

    for counter, (text, da) in enumerate(zip(texts, das)):
        delexs.append(delex.delexicalize(text, da, counter))

    write_toks(args.out_file, delexs)


if __name__ == '__main__':
    main()