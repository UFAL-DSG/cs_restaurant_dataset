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


def remove_dups_stable(l):
    """Remove duplicates from a list but keep the ordering.

    @return: Iterator over unique values in the list
    """
    seen = set()
    for i in l:
        if i not in seen:
            yield i
            seen.add(i)

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


def write_toks(file_name, data, capitalize=True, detok=True, lowercase=False):
    with codecs.open(file_name, 'w', encoding='UTF-8') as fh:
        for inst in data:
            # lowercase everything except placeholders
            if lowercase:
                inst = [tok.lower() if not tok.startswith('X-') else tok for tok in inst]
            sent = ' '.join(inst)
            # join -s, -ly
            sent = re.sub(r'child -s', 'children', sent)
            sent = re.sub(r' -s', 's', sent)
            sent = re.sub(r' -ly', 'ly', sent)
            sent = re.sub(r'\s+', ' ', sent)
            # fix capitalization
            if capitalize:
                sent = re.sub(r'( [.?!] [a-z])', lambda m: m.group(1).upper(), sent)
                sent = re.sub(r' (Ok|ok|i) ', lambda m: ' ' + m.group(1).upper() + ' ', sent)
                sent = sent[0].upper() + sent[1:]
            # fix spacing
            if detok:
                sent = re.sub(r' ([?.,\'])', r'\1', sent)
            # print the output
            print >> fh, sent


def write_das(file_name, das):
    with codecs.open(file_name, 'w', encoding='UTF-8') as fh:
        for da in das:
            da_str = '&'.join(unicode(dai) for dai in da)
            print >> fh, da_str


def write_texts(file_name, texts):
    with codecs.open(file_name, 'wb', 'UTF-8') as fh:
        for text in texts:
            print >> fh, text


def load_texts(file_name):
    data = []
    with codecs.open(file_name, 'r', encoding='UTF-8') as fh:
        for line in fh:
            line = line.strip()
            data.append(line)
    return data


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

    def analyze(self, text):
        self.__tokenizer.setText(text)
        out = []
        while self.__tokenizer.nextSentence(self.__forms_buf, self.__tokens_buf):
            self.__tagger.tag(self.__forms_buf, self.__lemmas_buf)
            out.extend([(form, lemma.lemma, lemma.tag)
                        for (form, lemma) in zip(self.__forms_buf, self.__lemmas_buf)])
        return out


class Generator(object):
    """Morphodita generator wrapper, with support for inflecting
    noun phrases (stop/city names, personal names)."""

    def __init__(self, morpho_model):
        self.__morpho = Morpho.load(morpho_model)
        self.__out_buf = TaggedLemmasForms()

    def generate(self, lemma, tag_wildcard, capitalized=None):
        """Get variants for one word from the Morphodita generator. Returns
        empty list if nothing found in the dictionary."""
        # run the generation for this word
        self.__morpho.generate(lemma, tag_wildcard, self.__morpho.GUESSER, self.__out_buf)
        # see if we found any forms, return empty if not
        if not self.__out_buf:
            return []
        # prepare capitalization
        cap_func = lambda string: string
        if capitalized == True:
            cap_func = lambda string: string[0].upper() + string[1:]
        elif capitalized == False:
            cap_func = lambda string: string[0].lower() + string[1:]
        # process the results
        return [(cap_func(form_tag.form), form_tag.tag)
                for form_tag in self.__out_buf[0].forms]

    def inflect(self, words, case=None, person=None, number=None, gender=None):
        # use all genders for standalone adjectives (with adverbs at most)
        forms_tags = []
        prev_tag = ''
        for word in words:
            form_tag_list = self.__inflect_word(word, prev_tag, case, person, number, gender)
            if not form_tag_list:
                form_tag_list = [(word[0], word[2])]
            forms_tags.append(form_tag_list)
            prev_tag = word[2]
        return forms_tags

    def __inflect_word(self, word, prev_tag, case, person, number, gender, personal_names=False):
        """Inflect one word in the given case (return a list of variants,
        None if the generator fails)."""
        form, lemma, tag = word
        new_tag = None
        if person:
            new_tag = 'VB-P---' + person + 'P-AA---'
            if number:
                new_tag = new_tag[0:3] + number + new_tag[4:]
        # inflect each word in nominative not following a noun in nominative
        # (if current case is not nominative), avoid numbers
        elif (re.match(r'^[^C]...1', tag) and
                (not re.match(r'^NN..1', prev_tag) or personal_names) and
                form not in ['římská'] and
                (case != '1' or number)):
            # change the case in the tag, allow all variants
            new_tag = re.sub(r'^(....)1(.*).$', r'\g<1>' + case + r'\g<2>?', tag)
            if gender:
                new_tag = new_tag[0:2] + gender + new_tag[3:]
            if number:
                new_tag = new_tag[0:3] + number + new_tag[4:]
            # use both sg. and pl. numbers (by default for -ice)
            if (form.endswith('ice') and form[0] == form[0].upper() and
                    not re.match(r'(nemocnice|ulice|vrátnice)', form, re.IGNORECASE)):
                new_tag = new_tag[0:3] + '?' + new_tag[4:]
        if new_tag:
            # try inflecting, return empty list if not found in the dictionary
            # + filter out colloquial forms
            capitalized = form[0] == form[0].upper()
            new_forms_tags = [(form, tag) for (form, tag) in self.generate(lemma, new_tag, capitalized)
                              if not re.match(r'.*[3467]$', tag)]
            return new_forms_tags
        else:
            return [(form, tag)]


def trunc_lemma(lemma):

    lemma_trunc = re.sub(r'((?:(`|_;|_:|_,|_\^|))+)(`|_;|_:|_,|_\^).+$', r'\1', lemma)
    if not lemma_trunc:
        lemma_trunc = lemma
    lemma_trunc = re.sub(r'(.+)-[0-9].*$', r'\1', lemma_trunc)
    return lemma_trunc
