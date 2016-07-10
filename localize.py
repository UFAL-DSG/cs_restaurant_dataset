#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import codecs
import random
import re
import sys
from argparse import ArgumentParser

from recordclass import recordclass


class Abst(recordclass('Abst', ['slot', 'value', 'start', 'end'])):
    """Simple representation of a single abstraction instruction."""

    def __unicode__(self):
        quote = '"' if ' ' in self.value or ':' in self.value else ''
        return (self.slot + '=' + quote + self.value + quote + ':' +
                str(self.start) + '-' + str(self.end))

    @staticmethod
    def parse(string):
        m = re.match('([^=]*)=(.*):([0-9]+)-([0-9]+)$', string)
        slot = m.group(1)
        value = re.sub(r'^[\'"]', '', m.group(2))
        value = re.sub(r'[\'"]#?$', '', value)
        value = re.sub(r'"#? and "', ' and ', value)
        value = re.sub(r'_', ' ', value)
        start = int(m.group(3))
        end = int(m.group(4))
        return Abst(slot, value, start, end)


class DAI(recordclass('DAI', ['dat', 'slot', 'value'])):
    """Simple representation of a single dialogue act item."""

    def __unicode__(self):
        quote = '"' if ' ' in self.value or ':' in self.value else ''
        return (self.dat + '(' + (self.slot or '') +
                ('=' + quote + self.value + quote if self.value else '') + ')')

    @staticmethod
    def parse(string):
        m = re.match('^([a-z_?]+)\(([^=]*)(?:=(.*))?\)$', string)
        dat = m.group(1)
        slot = m.group(2)
        value = m.group(3) if m.group(3) is not None else ''
        value = re.sub(r'^[\'"]', '', value)
        value = re.sub(r'[\'"]#?$', '', value)
        value = re.sub(r'"#? and "', ' and ', value)
        value = re.sub(r'_', ' ', value)
        return DAI(dat, slot, value)


def load_toks(file_name):
    data = []
    with codecs.open(file_name, 'r', encoding='UTF-8') as fh:
        for line in fh:
            line = line.strip()
            data.append(line.split())
    return data


def load_abstrs(file_name):
    data = []
    with codecs.open(file_name, 'r', encoding='UTF-8') as fh:
        for line in fh:
            line = filter(bool, line.strip().split('\t'))
            data.append([Abst.parse(part) for part in line])
    return data


def load_dais(file_name):
    data = []
    with codecs.open(file_name, 'r', encoding='UTF-8') as fh:
        for line in fh:
            line = line.strip()
            dais = re.split(r'(?<=\))&', line)
            data.append([DAI.parse(dai) for dai in dais])
    return data



def write_toks(file_name, data):
    with codecs.open(file_name, 'w', encoding='UTF-8') as fh:
        for inst in data:
            sent = ' '.join(inst)
            # join -s, -ly
            sent = re.sub(r'child -s', 'children', sent)
            sent = re.sub(r' -s', 's', sent)
            sent = re.sub(r' -ly', 'ly', sent)
            sent = re.sub(r'\s+', ' ', sent)
            # fix capitalization
            sent = re.sub(r'( [.?!] [a-z])', lambda m: m.group(1).upper(), sent)
            sent = re.sub(r' (Ok|ok|i) ', lambda m: ' ' + m.group(1).upper() + ' ', sent)
            sent = sent[0].upper() + sent[1:]
            # fix spacing
            sent = re.sub(r' ([?.,\'])', r'\1', sent)
            # print the output
            print >> fh, sent


def write_das(file_name, das):
    with codecs.open(file_name, 'w', encoding='UTF-8') as fh:
        for da in das:
            da_str = '&'.join(unicode(dai) for dai in da)
            print >> fh, da_str


LOCALIZE = {

    'name': [
        'Ferdinanda', 'U Tučňáků', 'Kočár z Vídně', 'Švejk Restaurant', 'Green Spirit', 'Ananta',
        'Pivo & Basilico', 'U Konšelů', 'Místo', 'Café Kampus', 'Baráčnická rychta', 'Café Savoy',
        'BarBar',
    ],
    'area': [
        'Hradčany', 'Malá Strana', 'Staré Město', 'Vinohrady',
        'Žižkov', 'Dejvice', 'Nusle', 'Karlín', 'Smíchov'
    ],
    'food': [
        'Czech', 'Italian', 'Chinese', 'Asian', 'French', 'German', 'Turkish', 'Indian', 'vegetarian',
        'American', 'Mexican',
    ],
    'street': [
        'Karmelitská', 'Štefánikova', 'Újezd', 'Malostranské náměstí', 'Tržiště',
        'Žatecká', 'Kaprova', 'Náprstkova', 'Národní',
    ],
    'near': [
        'Prague Castle', 'Old Town Square', 'Charles Bridge', 'TV Tower',
        'Petřín Tower', 'Stromovka', 'Wenceslas Square', 'Powder Tower',
    ],
}


def process_sent(toks, abstrs, da):
    for abstr in abstrs:
        if abstr.start >= len(toks) or not toks[abstr.start].startswith('X-'):
            continue

        # assuming X-slot_name is the only "abstraction" token, so it's safe to replace just this one
        if abstr.slot in ['name', 'area', 'food', 'near']:
            toks[abstr.start] = random.choice(LOCALIZE[abstr.slot])
        elif abstr.slot == 'address':
            toks[abstr.start] = random.choice(LOCALIZE['street']) + (' %d' % random.randint(1, 50))
        elif abstr.slot == 'price':
            val = re.sub(r'([1-9][0-9]*)', r'\g<1>0', abstr.value)
            val = re.sub(r'euro', r'Kč', val)
            toks[abstr.start] = val
        elif abstr.slot == 'phone':
            val = '2%d' % random.randint(10000000, 99999999)
            toks[abstr.start] = val
        elif abstr.slot == 'postcode':
            val = '1%d 00' % random.randint(10, 69)
            toks[abstr.start] = val
        else:
            toks[abstr.start] = abstr.value

        dai = next(dai_ for dai_ in da if dai_.slot == abstr.slot)
        dai.value = toks[abstr.start]
    return toks, da


def text_key(toks):
    """Key for sentence comparison (punctuation/casing differences are taken into account)."""
    return ' '.join(toks)


def main():
    random.seed(1206)

    ap = ArgumentParser()

    ap.add_argument('text_file', type=str, help='Input delexicalized text file')
    ap.add_argument('abstr_file', type=str, help='Lexicalization instruction file')
    ap.add_argument('da_file', type=str, help='Input DA file')
    ap.add_argument('out_file', type=str, help='Output file')
    ap.add_argument('out_das_file', type=str, help='Output DA file')

    args = ap.parse_args()

    texts = load_toks(args.text_file)
    abstrs = load_abstrs(args.abstr_file)
    das = load_dais(args.da_file)

    data_keys = set()
    data = []
    das_out = []
    for text, abstr, da in zip(texts, abstrs, das):
        key = text_key(text)
        if key in data_keys:  # skip (delex) duplicates
            continue
        data_keys.add(key)
        text, da = process_sent(text, abstr, da)
        data.append(text)
        das_out.append(da)  # TODO DAs should be processed somehow

    write_toks(args.out_file, data)
    write_das(args.out_das_file, das_out)


if __name__ == '__main__':
    main()
