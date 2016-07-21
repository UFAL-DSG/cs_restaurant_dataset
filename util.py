#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from ufal.morphodita import Tagger, Forms, TaggedLemmas, TokenRanges, Morpho, TaggedLemmasForms
from recordclass import recordclass
import re
import codecs


"""
REPRESENTATION
"""


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
        if not value.startswith('X-') and value != 'dont_care':
            value = re.sub(r'_', ' ', value)
        return DAI(dat, slot, value)


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


"""
I/O
"""


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


"""
Morphology
"""


class Analyzer(object):
    """Morphodita analyzer/tagger wrapper."""

    def __init__(self, tagger_model):
        self.__tagger = Tagger.load(tagger_model)
        self.__tokenizer = self.__tagger.newTokenizer()
        self.__forms_buf = Forms()
        self.__tokens_buf = TokenRanges()
        self.__lemmas_buf = TaggedLemmas()

    def analyze(self, stop_text):
        self.__tokenizer.setText(stop_text)
        out = []
        while self.__tokenizer.nextSentence(self.__forms_buf, self.__tokens_buf):
            self.__tagger.tag(self.__forms_buf, self.__lemmas_buf)
            out.extend([(form, lemma.lemma, lemma.tag)
                        for (form, lemma) in zip(self.__forms_buf, self.__lemmas_buf)])
        return out


def trunc_lemma(lemma):

    lemma_trunc = re.sub(r'((?:(`|_;|_:|_,|_\^|))+)(`|_;|_:|_,|_\^).+$', r'\1', lemma)
    if not lemma_trunc:
        lemma_trunc = lemma
    lemma_trunc = re.sub(r'(.+)-[0-9].*$', r'\1', lemma_trunc)
    return lemma_trunc
