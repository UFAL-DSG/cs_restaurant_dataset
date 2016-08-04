#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import codecs
import re
from argparse import ArgumentParser

from itertools import product
from util import Analyzer, trunc_lemma, load_dais, load_texts, write_toks, DAI
import sys
import json

from tgen.logf import log_info
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


class Delexicalizer(object):

    def __init__(self, slots, surface_forms, tagger_model, tagger_overrides, output_format='plain'):
        self.slots = slots.split(',')
        self.surface_forms = None
        if surface_forms:
            log_info("Loading surface forms...")
            with codecs.open(surface_forms, 'rb', 'UTF-8') as fh:
                self.surface_forms = json.load(fh)
        self.tagger_overrides = None
        if tagger_overrides:
            log_info("Loading tagger overrides...")
            with codecs.open(tagger_overrides, 'rb', 'UTF-8') as fh:
                self.tagger_overrides = json.load(fh)
        log_info("Loading tagger...")
        self.analyzer = Analyzer(tagger_model)
        self.output_format = output_format

    def delexicalize_text(self, text, da, counter=-1):
        """Delexicalize a single sentence (given the corresponding DA)."""
        # run Morphodita
        analysis = self.analyzer.analyze(text)
        # apply overrides
        if self.tagger_overrides:
            for pos, (form, lemma, tag) in enumerate(analysis):
                lc_form = form.lower()
                lc_lemma = trunc_lemma(lemma).lower()
                if (lc_form in self.tagger_overrides and
                        lc_lemma != self.tagger_overrides[lc_form][0]):
                    analysis[pos] = (form,
                                     self.tagger_overrides[lc_form][0],
                                     self.tagger_overrides[lc_form][1])
        # truncate and simplify
        lemmas = [trunc_lemma(tok[1]).lower() for tok in analysis]
        tags = [tok[2] for tok in analysis]
        delex = [tok[0] for tok in analysis]
        vals_to_forms = []
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
                    vals_to_forms.append((dai.slot, dai.value, form, delex[pos:pos+len(sf)]))
                    delex[pos] = 'X-' + dai.slot + form
                    delex[pos+1:pos+len(sf)] = [None] * (len(sf) - 1)
                    break

            if not found:
                # print out everything that couldn't be found -- error checking in the set
                print >> sys.stderr, (unicode(counter) + ': Not found: ' + dai.value + ' | ' +
                                      unicode(da) + ' | ' + text)
                print >> sys.stderr, 'Lemmas: ' + ' '.join(lemmas)
                print >> sys.stderr

        lemmas = [re.sub(r'/.*', r'', tok)
                  if (tok is not None and tok.startswith('X-'))
                  else lemma.lower() + (".NEG" if tag[10] == "N" else "")
                  for tok, lemma, tag in zip(delex, lemmas, tags)]
        if self.output_format == 'factors':
            return ([(tok, lemma, tag)
                    for tok, lemma, tag in zip(delex, lemmas, tags)
                    if tok is not None],
                    vals_to_forms)
        if self.output_format == 'lemma':
            return [lemma for tok, lemma in zip(delex, lemmas) if tok is not None]
        return [tok for tok in delex if tok is not None]

    def delexicalize_da(self, da):
        """Delexicalize a single DA."""
        da = [DAI(dai.dat, dai.slot, dai.value) for dai in da]  # deep copy
        # now delex the values
        for dai in da:
            if dai.slot not in self.slots and (dai.slot != 'address' or 'street' not in self.slots):
                continue
            if not dai.value or dai.value in ['dont care', 'dont_care', 'none']:
                continue
            dai.value = 'X-' + dai.slot
        return da

    def get_surface_forms(self, slot, value):
        """Get all possible surface forms (lemmas) for the given slot and value.
        Works around coordination, price templates, and address (where only street names
        must be in the surface forms list)."""

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
            tag = next(iter(reversed([t for t in tags[pos:pos+len(sf)] if re.match(r'....[2-7]', t)])), None)
            if not tag:
                tag = next(iter(reversed([t for t in tags[pos:pos+len(sf)] if re.match(r'....1', t)])), None)
            if not tag:
                return ''
            return '/n:' + tag[4]
        if (re.match(r'^[NA]', tags[pos]) or
                (pos < len(tags) - 1 and
                 re.match(r'^D', tags[pos]) and
                 re.match(r'^[NA]', tags[pos + 1]))):
            tag = next(iter([t for t in tags[pos:pos+len(sf)] if re.match(r'....[1-7]', t)]), None)
            if not tag:
                return ''
            return '/n:' + tag[4]

        if re.match(r'^D', tags[pos]):
            return '/adv'

        if re.match(r'^V', tags[pos]):
            return '/v:fin'

        return ''


def main():

    ap = ArgumentParser()

    ap.add_argument('-s', '--slots', type=str, help='List of slots to delexicalize')
    ap.add_argument('-f', '--surface-forms', type=str, help='Input file with surface forms for slot values')
    ap.add_argument('-t', '--tagger-model', type=str, help='Path to Morphodita tagger model')
    ap.add_argument('-o', '--tagger-overrides', type=str, help='Path to a JSON file with tagger overrides')
    ap.add_argument('-l', '--lemma-output', action='store_true', help='Output only lemmas instead of tokens?')
    ap.add_argument('text_file', type=str, help='Input lexicalized text file')
    ap.add_argument('da_file', type=str, help='Input DA file')
    ap.add_argument('out_file', type=str, help='Output delexicalized text file')

    args = ap.parse_args()

    delex = Delexicalizer(args.slots, args.surface_forms, args.tagger_model,
                          'lemma' if args.lemma_output else 'plain')

    texts = load_texts(args.text_file)
    das = load_dais(args.da_file)
    delexs = []

    for counter, (text, da) in enumerate(zip(texts, das)):
        delexs.append(delex.delexicalize_text(text, da, counter))

    write_toks(args.out_file, delexs)


if __name__ == '__main__':
    main()
